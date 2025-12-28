#!/usr/bin/env python3
"""
Script to remove broken div tags and implement working bordered sections
"""

import re

# Read the file
with open('app.py', 'r') as f:
    content = f.read()

# Remove all standalone opening div tags for section boxes
content = re.sub(r"st\.markdown\('<div class=\"section-box-green\">', unsafe_allow_html=True\).*?\n", "", content)
content = re.sub(r"st\.markdown\('<div class=\"section-box-blue\">', unsafe_allow_html=True\).*?\n", "", content)

# Remove all standalone closing div tags
content = re.sub(r"st\.markdown\('</div>', unsafe_allow_html=True\).*?\n", "", content)

# Remove part-container div tags
content = re.sub(r"st\.markdown\('<div class=\"part-container\">', unsafe_allow_html=True\).*?\n", "", content)

# Write back
with open('app.py', 'w') as f:
    f.write(content)

print("✅ Removed all broken div tags")
