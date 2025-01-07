#!/usr/bin/env python3

import os
import sys
from fddimage import Filesystem

ryba_file = "os-t34.fdd"
files_to_put = []
output_file = None

launchpath = os.path.dirname(sys.argv[0])
ryba_file = os.path.join(launchpath, ryba_file)

try:
    borrow = None
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i].strip()
        if borrow:
            borrow(arg)
            borrow = None
            i += 1
            continue

        if arg.startswith('-'):
            if arg == '-h':
                raise Exception("halp")
            elif arg == '-r':  # user ryba
                borrow = lambda v: globals().update(ryba_file=v)
            elif arg == '-i':  # file to add to filesystem
                borrow = lambda v: files_to_put.append(v)
            elif arg == '-o':  # output file
                borrow = lambda v: globals().update(output_file=v)
            else:
                print(f'arg: "{arg}" does not compute')
                raise Exception("hapl")
        else:
            print(f'arg: "{arg}" does not compute')
            raise Exception("hapl")
        i += 1

    if not len(files_to_put) or not output_file:
        raise Exception("hapl")

except Exception as e:
    print('Usage: fddutil -i file1 -i file2... -o output.fdd')
    sys.exit(0)

try:
    with open(ryba_file, 'rb') as f:
        ryba_data = f.read()
except Exception as e:
    print(f'Error reading ryba file: {ryba_file}')
    sys.exit(1)

fdd = Filesystem().from_array(ryba_data)
print('Contents of ryba stomach:')
fdd.list_dir()

for name in files_to_put:
    try:
        with open(name, 'rb') as f:
            data = f.read()
    except Exception as e:
        print(f'Could not read file {name}, it\'s numberwang')
        sys.exit(1)

    basename = os.path.basename(name)
    fdd.save_file(basename, data)
    print(f'Saved file {basename} to FDD image ({len(data)} bytes)')

try:
    with open(output_file, 'wb') as f:
        f.write(bytes(fdd.bytes))
    print(f'FDD image written to: {output_file}')
except Exception as e:
    print(f'Error writing FDD to: {output_file}')
    sys.exit(1)