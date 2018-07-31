# SramAnalyzer
This tool will analyze the startup values of SRAM of embedded devices and display statistical information about them. The startup values of SRAM can be used to build [physical uncloneable functions (PUFs)](https://en.wikipedia.org/wiki/Physical_unclonable_function). To extract the uninitialized SRAM values of an embedded devices, you'll need a JTAG probe. As an example the project contains the startup values of four [STM32F401RE](https://www.st.com/en/evaluation-tools/nucleo-f401re.html) boards.

## How to install
1. Clone this repository: `git clone https://github.com/TimothyClaeys/SramAnalyzer.git`
2. Move into the clone repository: `cd SramAnalyzer`
3. Install the python package with pip: `pip3 install -e .`
4. Test if everything works by typing `sram_tools` on the command line.

## How to use
### Pre-use
The startup values of four different embedded devices are provided as an example. Before you can run any of the statistical methods or generate bitmaps, `sram_tools` must first generate some cache files. This is necessary to speed up to computation of the statistics.
Generating the cache files can be done by running (this will take a few seconds):

`sram_tools --sram_dir SRAM_PRINTS/ analyze Timothy`.

You can also analyze and generate cache files for multiple devices at once by specifying mutliple devices:

`sram_tools --sram_dir SRAM_PRINTS/ analyze Andrzej Timothy Franck Pierre`

### Generating bitmaps
`sram_tools` allows you to generate bitmaps of the SRAM startup values. You can calculate either the entropy or probability per sram cell. The calculated value of every cell will than be converted into a grayscale value for one pixel. High entropy corresponds to clear pixels, while low entropy corresponds to dark pixels.

Example, entropy bitmap of 96Kb of SRAM startup values: 

`sram_tools --sram_dir SRAM_PRINTS/ bitmap simple --be Timothy`

Example, probability bitmap of 96Kb of SRAM startup values: 

`sram_tools --sram_dir SRAM_PRINTS/ bitmap simple --bp Timothy`
