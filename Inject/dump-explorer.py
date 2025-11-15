#!/usr/bin/env python3
import re
from bs4 import BeautifulSoup
import sys
import os

# The user-provided file name will now be taken from command-line arguments

def find_textarea_div_info(file_path):
    """
    Parses HTML content from the given file path to find all <textarea> elements 
    and reports information about their immediate parent <div> containers.
    """
    try:
        # Read the entire file content from the specified path
        with open(file_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
    except FileNotFoundError:
        print(f"Error: The file '{file_path}' was not found.")
        print("Please ensure the file path is correct.")
        return
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    # Initialize BeautifulSoup parser
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Find all <textarea> elements in the document
    textareas = soup.find_all('textarea')

    if not textareas:
        print(f"No <textarea> elements were found in '{file_path}'.")
        return

    print(f"--- Found {len(textareas)} <textarea> elements in '{file_path}' ---")
    
    # List to store the relevant div info for summary
    div_info_list = []
    
    for i, textarea in enumerate(textareas):
        # 1. Get Textarea info (ID and Name are useful for targeting)
        textarea_id = textarea.get('id', 'N/A')
        textarea_name = textarea.get('name', 'N/A')
        
        # 2. Find the immediate parent <div>
        parent_div = textarea.find_parent('div')
        
        div_info = {
            'tag': 'N/A',
            'id': 'N/A',
            'class': 'N/A',
        }
        
        if parent_div:
            # 3. Get Parent Div info
            div_info['tag'] = parent_div.name
            div_info['id'] = parent_div.get('id', 'None')
            
            # The 'class' attribute returns a list, join it for cleaner output
            classes = parent_div.get('class')
            if classes:
                div_info['class'] = ' '.join(classes)
            else:
                div_info['class'] = 'None'
            
            # Store primary info for summary
            div_info_list.append({
                'index': i + 1,
                'textarea_id': textarea_id,
                'div_id': div_info['id'],
                'div_class': div_info['class']
            })
        
        
        print(f"\n[TEXTAREA {i + 1}]")
        print(f"  > Textarea ID:   {textarea_id}")
        print(f"  > Textarea Name: {textarea_name}")
        
        if parent_div:
            print(f"  > Immediate Parent <{div_info['tag']}> Info:")
            print(f"    - ID:    {div_info['id']}")
            print(f"    - Class: {div_info['class']}")
        else:
            print("  > No immediate parent <div> found.")
            
        # Optional: Print the first 50 characters of the content if present
        if textarea.string:
             # Strip whitespace and print a snippet
            snippet = textarea.string.strip()
            print(f"  > Content Snippet: '{snippet[:50]}...'")
            
        # Optional: Print the full path (ancestors) for better context
        path = []
        element = textarea
        # Traverse up from the textarea until we hit the <html> tag or run out of ancestors
        while element and element.name != 'html':
            id_attr = element.get('id', '')
            class_attr = ' '.join(element.get('class', []))
            
            # Construct a CSS-selector like path segment
            segment = element.name
            if id_attr:
                segment += f"#{id_attr}"
            elif class_attr:
                # Use the first class as a primary identifier if no ID
                segment += f".{class_attr.split()[0]}"
            
            path.append(segment)
            element = element.parent
        
        # Show path from 2 levels up to the immediate parent
        # path[1] is the parent, path[2] is the grandparent
        print(f"  > Ancestor Path (Parent > Grandparent): {' > '.join(path[1:3] or path[:1])} > ...")
            
    # Print the final summary of the target divs
    if div_info_list:
        print("\n" + "="*50)
        print("SUMMARY: TARGET DIV INFORMATION")
        print("="*50)
        for item in div_info_list:
            print(f"Textarea {item['index']}:")
            print(f"  Target Div ID:    {item['div_id']}")
            print(f"  Target Div Class: {item['div_class']}")
        print("="*50)


def main():
    """
    Main execution function to handle command line arguments and run the analysis.
    """
    # 1. Check for the BeautifulSoup dependency first
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("Error: The 'beautifulsoup4' library is not installed.")
        print("You must install it using: pip install beautifulsoup4")
        sys.exit(1)
        
    # 2. Check for the correct number of command-line arguments
    if len(sys.argv) < 2:
        print("Usage: ./textarea_finder.py <path_to_html_file>")
        print("Example: ./textarea_finder.py gphotos_dump_1763247510.html")
        sys.exit(1)

    file_to_analyze = sys.argv[1]
    
    print(f"Attempting to analyze file: {file_to_analyze}")
    find_textarea_div_info(file_to_analyze)

if __name__ == "__main__":
    main()
