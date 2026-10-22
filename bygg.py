"""Bygger Månhjälten till ett program som går att starta utan Python.

Kör på den dator du vill bygga för (Windows, macOS eller Linux):

    pip install -r requirements.txt pyinstaller
    python bygg.py

Resultatet hamnar i mappen dist/.
"""
import os
import sys

import PyInstaller.__main__

PyInstaller.__main__.run([
    'manhjalten.py',
    '--name', 'Manhjalten',
    '--noconfirm',
    '--clean',
    '--windowed',  # inget terminalfönster, och en .app på macOS
    '--add-data', f'ljud{os.pathsep}ljud',
    '--collect-all', 'ursina',
    '--collect-all', 'panda3d',
    *(['--osx-bundle-identifier', 'se.barnkyrkan.manhjalten'] if sys.platform == 'darwin' else []),
])
