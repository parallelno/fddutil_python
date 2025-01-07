# FDDUTIL-PYTHON README.md

# FDD Utility Tool

This project is a Python implementation of the FDD utility tool, originally written in JavaScript by Svofski (https://github.com/svofski/v06c-fddutil). The tool is designed to handle reading and writing FDD (Floppy Disk Drive) images, allowing users to manage files within these images.

## Project Structure

The project consists of the following files:

- `src/fddutil.py`: Contains the main functionality of the FDD utility tool, including reading and writing FDD images, processing command-line arguments, and managing files to be added to the FDD image.
  
- `src/fddimage.py`: Defines the classes and functions necessary for handling the FDD image structure. This includes classes for managing headers, directories, and the filesystem.

## Usage

To use the FDD utility tool, run the following command:

```
python src/fddutil.py -i <input_file1> -i <input_file2> -r<input_base_file.fdd> ... -o <output_file.fdd>
```

- `-i`: Specify the files to add to the FDD image.
- `-o`: Specify the output FDD image file.
- `-r`: Specify the input base FDD image file. Not required.

## License

This project is licensed under the MIT License. See the LICENSE file for more details.