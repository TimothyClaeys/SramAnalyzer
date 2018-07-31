from setuptools import setup

setup(
    name='sram_tools',
    version='0.1',
    py_modules=['sram_tools'],
    install_requires=[
        'Click',
        'pillow',
        'matplotlib'
    ],
    entry_points='''
        [console_scripts]
        sram_tools=sramanalyzer:cli
    ''',
)