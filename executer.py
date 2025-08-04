import os
import subprocess

# Get the folder where this script is located
current_dir = os.path.dirname(os.path.abspath(__file__))

# Build full path to the file you want to run
script_to_run = os.path.join(current_dir, "manager.py")

# Path to virtual environment's Python executable
venv_python = os.path.join(current_dir, "myenv", "Scripts", "python.exe")

# Run the file
subprocess.run([venv_python, script_to_run], cwd=current_dir)
