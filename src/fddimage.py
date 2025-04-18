import math
import utils.build as build

# Physical sector size
FDD_SIDES = 2
FDD_TRACKS_PER_SIDE = 82
FDD_SECTORS_PER_TRACK = 5
FDD_SECTOR_LEN = 1024
FDD_SIZE = FDD_SIDES * FDD_TRACKS_PER_SIDE * FDD_SECTORS_PER_TRACK * FDD_SECTOR_LEN

STATUS_FILE_EXISTS			= 0x0F
STATUS_FILE_DOESNT_EXISTS	= 0x10
EMPTY_MARKER 				= 0xE5

RECORD_SIZE					= 0x80 # if MDHeader.records < 0x80 then this is the last extent of the file

# Directory structure
DIRECTORY_START_OFFSET		= 0xA000 # Directory starts at 40960
DIRECTORY_END_OFFSET		= 0xB000 # Directory ends at 45056
ENTRY_SIZE		 			= 32 # Size of each directory entry
MAX_ENTRIES		 			= (DIRECTORY_END_OFFSET - DIRECTORY_START_OFFSET) // ENTRY_SIZE # 128 entries (each file can take more than 1 entry) in directory

# File system
CLUSTER_LEN					= 2048

# MicroDOS ? header
class MDHeader:
	def __init__(self):
		self.status = 0 	# 0x0 - 0x0F: file exists,
							# 0xE5 - deleted

		self.filename = ""	# 8 bytes of 7-bit ASCII characters
		self.filetype = ""	# 3 bytes of 7-bit ASCII characters
		self.extent = 0		# Extent counter. If a file grows above 16k, then it will have multiple
							# directory entries. The first entry has Extent=0, the second has Extent=1 etc.
							# EX ranges from 0 to 31, thus allowing files up to 512k. CP/M 1.4 only
							# allows 256k discs anyway.

		self.unknown1 = 0	# Reserved, always 0
		self.unknown2 = 0	# Reserved, always 0

		self.records = 0    # Number of records (1 record=128 bytes) used in this extent. If it is
							# >= 80h, this extent is full and there may be another one on the disc.
							# File lengths are only saved to the nearest 128 bytes.

		self.fat = [0] * 8  # Initialize FAT with 8 elements
		self.mapped = None
		self.Index = 0

	def from_array(self, _data : memoryview):
		self.status = _data[0]
		# Convert bytes to string without assuming ASCII encoding
		self.filename = ''.join(chr(b) for b in _data[1:9]).strip()
		self.filetype = ''.join(chr(b) for b in _data[9:12]).strip()
		self.extent = _data[12]
		self.unknown1 = _data[13]
		self.unknown2 = _data[14]
		self.records = _data[15]

		# it's equivalent to:
		fat_bytes = _data[16:32]
		self.fat = [
			(fat_bytes[j] | (fat_bytes[j + 1] << 8))
			for j in range(0, 16, 2)
		]
		# shorter but less readable
		#self.fat = [struct.unpack('<H', _data[16 + 2 * i:18 + 2 * i])[0] for i in range(8)]

		self.mapped = _data
		return self

	def to_bytes(self, _destination : memoryview):
		_destination[0] = self.status
		name = self.filename.ljust(8)
		for i in range(8):
			_destination[1 + i] = ord(name[i])
		ext = self.filetype.ljust(3)
		for i in range(3):
			_destination[9 + i] = ord(ext[i])
		_destination[12] = self.extent
		_destination[13] = self.unknown1
		_destination[14] = self.unknown2
		_destination[15] = self.records
		for i in range(8):
			_destination[16 + 2 * i] = self.fat[i] & 0xff
			_destination[16 + 2 * i + 1] = (self.fat[i] >> 8) & 0xff

	def from_name(self, _filename : str):
		nameext = _filename.upper().split(".")
		self.filename = nameext[0]
		self.filetype = nameext[1] if len(nameext) > 1 else ""
		return self

class DirectoryEntry:
	def __init__(self, _filesystem):
		self.filesystem : Filesystem = _filesystem
		self.Header : MDHeader = None
		self.Chain = []
		self.Size = 0

	def from_header(self, header : MDHeader):
		self.Header : MDHeader = header
		self.Chain = []
		lastHeader = self.find_last_header(header)
		if lastHeader:
			self.Size = lastHeader.extent * 2048 * 8 + lastHeader.records * 128
		return self

	def find_last_header(self, sought : MDHeader) -> MDHeader:
		lastHeader = None
		def callback(_header):
			if _header.status <= STATUS_FILE_EXISTS and _header.filename == sought.filename and _header.filetype == sought.filetype:
				self.Chain.extend(_header.fat)
				if _header.records < RECORD_SIZE:
					nonlocal lastHeader
					lastHeader = _header
					return True
			return False
		self.filesystem.read_dir(callback)
		return lastHeader

class Filesystem:
	def __init__(self, _size = 0):
		# erase disk data
		self.bytes = bytearray([EMPTY_MARKER ] * _size)

	def from_array(self, _data):
		if len(_data) > len(self.bytes):
			self.bytes = bytearray(len(_data))
		self.bytes[:] = _data
		return self

	def map_sector(self, _trackID, _sideID, _sector):

		sectors = FDD_SECTORS_PER_TRACK * (_trackID * FDD_SIDES + _sideID)
		sectorAdjusted = max(0, _sector - 1)  # In CHS addressing the sector numbers always start at 1, but in the data buffer the sector numbers always start at 0.
		offset = (sectors + sectorAdjusted) * FDD_SECTOR_LEN

		return memoryview(self.bytes)[offset:offset + FDD_SECTOR_LEN]

	def read_dir(self, _file_callback):
		SECTOR_SIZE = 32

		for position in range(DIRECTORY_START_OFFSET, DIRECTORY_END_OFFSET, SECTOR_SIZE):
			header = MDHeader()
			header.from_array(
				memoryview(self.bytes)[position:position + SECTOR_SIZE]
			)
			header.Index = (position - DIRECTORY_START_OFFSET) // SECTOR_SIZE
			if _file_callback(header):
				break

	def cluster_to_ths(self, cluster):
		track = 8 + (cluster // 5)
		head = track % 2
		track >>= 1
		sector = 1 + (cluster % 5)
		return (track, head, sector)
	
	def list_dir(self):
		def callback(_header):
			if _header.status <= STATUS_FILE_EXISTS and _header.extent == 0:
				d = DirectoryEntry(self).from_header(_header)
				build.printc(f"{_header.filename}.{_header.filetype}, size: {d.Size} bytes", build.TextColor.GRAY)
			return False
		self.read_dir(callback)

	MAXCLUST = 390

	def build_available_chain(self):
		used_clusters = bytearray(self.MAXCLUST)
		def callback(header):
			if header.status <= STATUS_FILE_EXISTS:
				for cluster_index in header.fat:
					used_clusters[cluster_index] = 1
			return False
		self.read_dir(callback)

		unusedClusters = []
		for cluster_index in range(2, len(used_clusters)):
			if used_clusters[cluster_index] == 0:
				unusedClusters.append(cluster_index)
		return unusedClusters

	def save_file(self, _fileName, _fileBytes : int):
		available_clusters = self.build_available_chain()
		free_space = len(available_clusters) * CLUSTER_LEN

		if free_space < len(_fileBytes):
			build.exit_error(f"Disk full, free space: {free_space} bytes, remaining clusters: {len(available_clusters)}")
			return False

		header = MDHeader().from_name(_fileName)

		# find header index?
		def allocate_clusters(_filesystem, _header, _available_clusters : int, _remaining_bytes : int):
			cluster_index = 0
			extent = 0
			def callback(existing_header):
				nonlocal cluster_index, extent, _remaining_bytes
				if existing_header.status >= STATUS_FILE_DOESNT_EXISTS:  # take this header
					old_file = ""
					if (existing_header.filename != "åååååååå" or existing_header.filetype != "ååå"):
						old_file = existing_header.filename + "." + existing_header.filetype 

					build.printc(f"Saved to header: {existing_header.Index}. Previously stored file: {old_file}", build.TextColor.GRAY)
					# allocate clusters
					_header.records = math.ceil(_remaining_bytes // 128)
					_header.extent = extent
					extent += 1
					_header.records = min(_header.records, RECORD_SIZE)

					for i in range(8):
						_header.fat[i] = _available_clusters[cluster_index] if _remaining_bytes > 0 else 0
						if _remaining_bytes > 0:
							_remaining_bytes -= 2048
							cluster_index += 1
					_header.to_bytes(existing_header.mapped)
					if _remaining_bytes <= 0:
						return True  # all mapped
				return False
			_filesystem.read_dir(callback)
			return cluster_index

		header_index = allocate_clusters(self, header, available_clusters, len(_fileBytes))

		if header_index != 0:
			srcptr = 0
			for cluster_index in range(header_index):
				if srcptr >= len(_fileBytes):
					break

				clust = available_clusters[cluster_index] << 1
				for i in range(2):
					track, head, sector = self.cluster_to_ths(clust + i)
					mapped = self.map_sector(track, head, sector)

					for p in range(1024):
						if srcptr >= len(_fileBytes):
							break
						mapped[p] = _fileBytes[srcptr]
						srcptr += 1
	
		
		available_clusters = self.build_available_chain()
		free_space = len(available_clusters) * CLUSTER_LEN
		return free_space
	
	'''
	def find_file(self, filename):
		header = MDHeader().from_name(filename.upper())
		result = None
		def callback(h):
			if h.status <= STATUS_FILE_EXISTS and h.filename == header.filename and h.filetype == header.filetype:
				nonlocal result
				result = h
				return True
			return False
		self.read_dir(callback)
		if result:
			return DirectoryEntry(self).from_header(result)
		return None
	'''
	
	'''
	def read_bytes(self, dirent):
		result = bytearray(dirent.Size)
		resultptr = 0
		for clust in dirent.Chain:
			clust <<= 1
			if clust < 2:
				break
			for i in range(2):
				track, head, sector = self.cluster_to_ths(clust + i)
				mapped = self.map_sector(track, head, sector)
				result[resultptr:resultptr + 1024] = mapped
				resultptr += 1024
		return result

	def readFile(self, name):
		dirent = self.find_file(name)
		if dirent:
			return self.read_bytes(dirent)
		return None
	'''

'''
def test_filesystem(_filesystem):
	print("List all files:")
	_filesystem.read_dir(lambda h: print(f"File: {h.filename}.{h.filetype} header={h} dirent={DirectoryEntry(_filesystem).from_header(h)}") if h.status <= STATUS_FILE_EXISTS and h.extent == 0 else False)

	print("Find pip.com:")
	d = _filesystem.find_file("pip.com")
	if d:
		print("Found:", d)
	else:
		raise Exception('File was not found')

	bytes = _filesystem.read_bytes(d)
	expected = [0xc3, 0xce, 0x4, 0xc9, 0x0, 0x0, 0xc9, 0x0, 0x0, 0x1a, 0x0, 0x0, 0x0, 0x0, 0x0, 0x0, 0x28, 0x49, 0x4e, 0x50, 0x3a, 0x2f, 0x4f, 0x55, 0x54, 0x3a, 0x53, 0x50, 0x41, 0x43, 0x45, 0x29]
	print("Read bytes:", ' '.join(f"{b:02x}" for b in bytes[:32]))

	for i in range(len(expected)):
		if bytes[i] != expected[i]:
			print(f"Contents mismatch: expected 0x{expected[i]:02x} got 0x{bytes[i]:02x}")
			break
	else:
		print("File reading seems to be ok")

	print("Which clusters are unallocated:")
	chain = _filesystem.build_available_chain()
	print(chain)

	print("Creating new file")
	import random
	contents = bytearray([int(random.random() * 255) for _ in range(54321)])
	_filesystem.save_file("test.rnd", contents)

	print("List all files:")
	_filesystem.read_dir(lambda h: print(f"File: {h.filename}.{h.filetype} header={h} dirent={DirectoryEntry(_filesystem).from_header(h)}") if h.status <= STATUS_FILE_EXISTS and h.extent == 0 else False)

	print("Searching for new file:")
	d = _filesystem.find_file("test.rnd")
	if not d:
		print("test.rnd not found")
		raise Exception('')

	print("found, comparing contents")
	readcontents = _filesystem.readFile("test.rnd")
	if not readcontents:
		print("Could not read file")
		raise Exception('')

	for i in range(len(contents)):
		if contents[i] != readcontents[i]:
			print(f"Contents mismatch pos={i} expected={contents[i]:02x} got={readcontents[i]:02x}")
			raise Exception('')

	print("Which clusters are unallocated:")
	chain = _filesystem.build_available_chain()
	print(chain)

	print("All tests done")

if __name__ == "__main__":
	filesystem = Filesystem(1024 * 1024)
	test_filesystem(filesystem)
'''