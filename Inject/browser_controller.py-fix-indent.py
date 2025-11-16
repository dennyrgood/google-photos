# Save this as fix_indent.py
with open('browser_controller.py', 'r') as f:
    lines = f.readlines()

fixed = []
for line in lines:
    # If it's a method definition, ensure it has exactly 4 spaces
    if line.strip().startswith('def ') and 'class ' not in line:
        fixed.append('    ' + line.lstrip())
    else:
        fixed.append(line)

with open('browser_controller.py', 'w') as f:
    f.writelines(fixed)

print("Fixed indentation")
