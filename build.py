import PyInstaller.__main__
import os

if __name__ == '__main__':
    print("Building lce2je GUI...")
    
    icon_path = os.path.join('assets', 'logo', 'lce2je_logo_multi.ico')
    assets_data = os.path.join('assets', 'logo') + os.pathsep + os.path.join('assets', 'logo')
    
    args = [
        'gui_main.py',
        '--name=lce2je',
        '--windowed',
        f'--icon={icon_path}',
        f'--add-data={assets_data}',
        '--noconfirm',
        '--clean'
    ]
    args.append('--onefile')
    
    if os.name == 'nt':
        args.append('--version-file=version_info.txt')
        
    PyInstaller.__main__.run(args)
    
    print("\nBuild completed! The executable is located in the 'dist' folder.")
