import re

def update_print_syntax(file_path):
    with open(file_path, 'r') as file:
        file_contents = file.read()

    updated_contents = re.sub(r'print\s+([^\n]+)', r'print(\1)', file_contents)
 
    with open(file_path, 'w') as file:
        file.write(updated_contents)

if __name__ == "__main__":
    file_path = 'wifi_mac/RateAdapt.py'
    update_print_syntax(file_path)
