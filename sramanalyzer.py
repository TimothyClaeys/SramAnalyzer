import contextlib
import logging
import os
import re
from random import randint

import click
import numpy
from PIL import Image
from binascii import unhexlify


class DeviceSramMaps:
    sram_hex_maps = None
    sram_bin_maps = None


class SramAnalyzerConfig:
    devices = {}
    home_dir = None
    sram_dir = None


pass_config = click.make_pass_decorator(SramAnalyzerConfig, ensure=True)


@click.group()
@pass_config
@click.option('--sram_dir', default='.', help='Set directory of SRAM maps.')
@click.option('-v', '--verbose', is_flag=True, help='Use verbose mode.')
@click.option('--vv', is_flag=True, help='Use a more detailed verbose mode.')
def cli(config, sram_dir, verbose, vv):
    """

    Quickly analyze the SRAM startup values for an embedded device.\n
    ----------------------------------------------------------------\n
    All the hex memory dumps taken with Ride7 should be stored in a folder with the device's name with the extension
    '.dev'. When analyzing the SRAM of multiple devices, the tool should be launched from the parent directory where all
    the device folders are stored or the parent directory can be specified with the option '--sram_dir'.

    Example:\n
        SRAM_DUMPS/\n
            - DeviceName1.dev/\n
                - mem_dump1.hex\n
                - mem_dump2.hex\n
                - mem_dump3.hex\n
                - ...\n
            - DeviceName2.dev/\n
                - mem_dump1.hex\n
                - mem_dump2.hex\n
                - mem_dump3.hex\n

        > sram_tools --sram_dir SRAM_DUMPS/ [COMMAND] [ARGS]

    The first time using the tool, you should run: \n
    > sram_tools --sram_dir [PARENT_DIRECTORY] analyze\n
    This will generate the necessary cache files for all the other commands.
    """

    click.echo(" ___ ___    _   __  __     _   _  _   _   _ __   _________ ___  ")
    click.echo("/ __| _ \  /_\ |  \/  |   /_\ | \| | /_\ | |\ \ / /_  / __| _ \ ")
    click.echo("\__ \   / / _ \| |\/| |  / _ \| .` |/ _ \| |_\ V / / /| _||   / ")
    click.echo("|___/_|_\/_/ \_\_|  |_| /_/ \_\_|\_/_/ \_\____|_| /___|___|_|_\ ")
    click.echo("                                                                ")

    # set logging level
    if verbose:
        logging.basicConfig(format="[%(levelname)s] %(message)s", level=logging.INFO)
    if vv:
        logging.basicConfig(format="[%(levelname)s] %(message)s", level=logging.DEBUG)

    config.sram_dir = sram_dir
    config.home_dir = os.getcwd()

    # find all devices in SRAM directory
    devices = [dev for dev in os.listdir(sram_dir) if dev[-4:] == '.dev']

    # For every device found, get the memory maps and the possible cache files
    for dev in devices:
        path = os.path.join(config.sram_dir, dev)

        # register all sram memory maps and cached numpy files
        raw_memory_maps = [mm for mm in os.listdir(path) if mm[-4:] == '.hex' and mm[0] != '.']
        cached_memory_maps = [cmm for cmm in os.listdir(path) if cmm[-4:] == '.npy' and cmm[0] == '.']

        # for each device, store the found and cached memory maps
        mem_prints = DeviceSramMaps()
        mem_prints.sram_hex_maps = sorted(raw_memory_maps)
        mem_prints.sram_bin_maps = sorted(cached_memory_maps)
        config.devices[dev[:-4]] = mem_prints


@cli.command()
@pass_config
def ls(config):
    """ Print all discovered devices. """
    click.echo("Device names:")
    click.echo("--------------------")

    if len(config.devices) == 0:
        click.echo("No devices found.")

    for device in config.devices:
        click.echo("~> " + device)


def preprocess(config, dev):
    logging.info("%s\t| Prepocessing memory maps", dev)

    sram_sizes = []

    # build cache memory maps for every device
    with contextlib.ExitStack() as stack:
        fds_mm = [stack.enter_context(open(fname, 'r')) for fname in config.devices[dev].sram_hex_maps]
        for fd_mm in fds_mm:
            sram_lines = []
            for rline in fd_mm:
                mobj = re.match(r'^:10[0-9A-Z]{6}([0-9A-Z]*)[0-9A-Z]{2}$', rline, re.M)
                if mobj:
                    byteline = mobj.group(1)
                    bits = numpy.array(list("".join(format(b, '08b') for b in unhexlify(byteline))), dtype=numpy.uint8)
                    sram_lines.append(bits)
            sram_sizes.append(len(sram_lines) * len(sram_lines[0]))
            numpy.save('.' + fd_mm.name[:-4], numpy.array(sram_lines, dtype=numpy.uint8))

    cached_memory_maps = [cmm for cmm in os.listdir('.') if cmm[-4:] == '.npy' and cmm[0] == '.']
    config.devices[dev].sram_bin_maps = cached_memory_maps

    if len(set(sram_sizes)) > 1:
        raise Exception('Not all SRAM maps have equal length for device %s', dev)


@cli.command()
@click.argument("devices", nargs=-1)
@pass_config
def analyze(config, devices):
    """ Analyze the SRAM startup values and generate cache files. """
    results = []

    for dev in devices:
        try:
            path = os.path.join(config.sram_dir, dev + '.dev')
            os.chdir(path)
            preprocess(config, dev)
        except FileNotFoundError as err:
            click.echo("Could not find file: {}".format(path))
            exit(-1)

        logging.info("%s\t| Analyzing SRAM", dev)

        frequency_matrix = None

        try:
            for cf in config.devices[dev].sram_bin_maps:
                if frequency_matrix is None:
                    frequency_matrix = numpy.load(cf)
                else:
                    frequency_matrix += numpy.load(cf)
        except TypeError:
            click.echo("Couldn't load cache file %s into frequency matrix object" % cf)
            exit(-1)

        probability_matrix = frequency_matrix / len(config.devices[dev].sram_bin_maps)

        numpy.save("probs_map", probability_matrix)

        with numpy.errstate(divide='ignore', invalid='ignore'):
            entropy_matrix = - probability_matrix * numpy.log2(probability_matrix) - \
                             (1 - probability_matrix) * numpy.log2(1 - probability_matrix)

        entropy_matrix = numpy.nan_to_num(entropy_matrix)

        numpy.save("entropy_map", entropy_matrix)

        logging.info("%s\t| %f%% entropy per bit in device", dev,
                     (numpy.sum(entropy_matrix) / entropy_matrix.size) * 100)

        results.append((numpy.sum(entropy_matrix) / entropy_matrix.size) * 100)

        os.chdir(config.home_dir)

    click.echo("\nStatistical results:")
    click.echo("======================\n")

    click.echo("Device\t: Entropy (%)")
    click.echo("---------------------")
    for d, e in zip(devices, results):
        click.echo("%s\t: %f" % (d, e))


@cli.group()
@pass_config
def bitmap(config):
    """ Base command for bitmap operations. """
    pass


@bitmap.command()
@click.argument("devs", nargs=-1)
@click.option('-i', "--images", nargs=2, default=None, help="Specify two images to compare")
@click.option('-r', '--res', nargs=2, default=(768, 1024), help='Set resolution bitmap.')
@pass_config
def diff(config, devs, images, res):
    """ Analyze the differences between two SRAM prints from two different devices or the same device. """
    if len(devs) not in [1, 2]:
        raise Exception("Not the right amount of devices!")

    if len(devs) == 1:
        if len(images) == 2:
            image1 = os.path.join(config.sram_dir, devs[0] + ".dev", "." + images[0][:-4] + ".npy")
            image2 = os.path.join(config.sram_dir, devs[0] + ".dev", "." + images[1][:-4] + ".npy")
        else:
            # if not images specified, get two random images
            index1, index2 = -1, -1
            while index1 == index2:
                index1, index2 = randint(0, len(config.devices[devs[0]].sram_bin_maps) - 1), randint(0, len(
                    config.devices[devs[0]].sram_bin_maps) - 1)

            image1 = os.path.join(config.sram_dir, devs[0] + ".dev", config.devices[devs[0]].sram_bin_maps[index1])
            image2 = os.path.join(config.sram_dir, devs[0] + ".dev", config.devices[devs[0]].sram_bin_maps[index2])

        logging.info("%s\t| Difference between \"%s\" and \"%s\" ", devs[0], image1, image2)

        try:
            image1 = numpy.load(image1)
            image2 = numpy.load(image2)
        except FileNotFoundError:
            click.echo("Device was not found. Possible issues: \n"
                       " - Are you sure you spelled it correctly?\n"
                       " - Are you in SRAM working directory? (tip: try \'sram_tools --sram-dir [DIRECTORY] ls\')"
                       "")
            exit(-1)

        difference = numpy.abs(numpy.array(image1 - image2, dtype=numpy.int8))
        num_of_diff_bits = numpy.sum(difference)

        difference = numpy.array([(0, x * 255, 0) for x in difference.ravel()],
                                 dtype=[('r', numpy.uint8), ('g', numpy.uint8), ('b', numpy.uint8)]).reshape(
            (128, 6144))

        if res[0] * res[1] != difference.shape[0] * difference.shape[1]:
            raise Exception(
                "Invalid resolution! The total resolution must correspond to the total size of the SRAM memory,"
                " e.g 512 * 1536 = 96kB")

        im = Image.fromarray(difference.reshape(res[0], res[1]), mode='RGB')
        im.show(title="Diff bitmap")

    if len(devs) == 2:
        if len(images) == 2:
            image1 = os.path.join(config.sram_dir, devs[0] + ".dev", "." + images[0][:-4] + ".npy")
            image2 = os.path.join(config.sram_dir, devs[1] + ".dev", "." + images[1][:-4] + ".npy")
        else:
            # if not images specified, get two random images
            index1, index2 = -1, -1
            while index1 == index2:
                index1, index2 = randint(0, len(config.devices[devs[0]].sram_bin_maps) - 1), randint(0, len(
                    config.devices[devs[1]].sram_bin_maps) - 1)

            image1 = os.path.join(config.sram_dir, devs[0] + ".dev", config.devices[devs[0]].sram_bin_maps[index1])
            image2 = os.path.join(config.sram_dir, devs[1] + ".dev", config.devices[devs[1]].sram_bin_maps[index2])

        logging.info("%s\t| Selected memory print \"%s\" ", devs[0], image1)
        logging.info("%s\t| Selected memory print \"%s\" ", devs[1], image2)

        try:
            image1 = numpy.load(image1)
            image2 = numpy.load(image2)
        except FileNotFoundError:
            click.echo("Device was not found. Possible issues: \n"
                       " - Are you sure you spelled it correctly?\n"
                       " - Are you in SRAM working directory? (tip: try \'sram_tools --sram-dir [DIRECTORY] ls\')"
                       "")
            exit(-1)

        difference = numpy.abs(numpy.array(image1 - image2, dtype=numpy.int8))
        num_of_diff_bits = numpy.sum(difference)

        difference = numpy.array([(0, x * 255, 0) for x in difference.ravel()],
                                 dtype=[('r', numpy.uint8), ('g', numpy.uint8), ('b', numpy.uint8)]).reshape(
            (128, 6144))

        if res[0] * res[1] != difference.shape[0] * difference.shape[1]:
            raise Exception(
                "Invalid resolution! The total resolution must correspond to the total size of the SRAM memory,"
                " e.g 512 * 1536 = 96kB")

        im = Image.fromarray(difference.reshape(res[0], res[1]), mode='RGB')
        im.show(title="Diff bitmap")

    click.echo("Total number of different bits: %d (%f%%)" % (
        num_of_diff_bits, (num_of_diff_bits / (difference.shape[0] * difference.shape[1])) * 100))


@bitmap.command()
@click.option('--be', '--cumul_bitmap_entropy', is_flag=True, help='Show a cumulative bitmap of the entropy the SRAM.')
@click.option('--bp', '--cumul_bitmap_probability', is_flag=True,
              help='Show a cumulative bitmap of the probability the SRAM.')
@click.option('-r', '--res', nargs=2, default=(768, 1024), help='Set resolution bitmap.')
@click.argument("devices", nargs=-1)
@pass_config
def cumulative(config, devices, cumul_bitmap_entropy, cumul_bitmap_probability, res):
    """ Generate a cumulative bitmap for all the devices. """
    bitmap = None
    try:
        if cumul_bitmap_entropy:
            for dev in devices:
                entropy_file = os.path.join(config.sram_dir, dev + ".dev", "entropy_map.npy")
                if bitmap is None:
                    bitmap = numpy.load(entropy_file)
                else:
                    bitmap += numpy.load(entropy_file)

                logging.info("%s\t| Generating cumulative entropy bitmap", dev)
        elif cumul_bitmap_probability:
            for dev in devices:
                probs_file = os.path.join(config.sram_dir, dev + ".dev", "probs_map.npy")
                if bitmap is None:
                    bitmap = numpy.load(probs_file)
                else:
                    bitmap += numpy.load(probs_file)

                logging.info("%s\t| Generating cumulative probability bitmap", dev)
        else:
            click.echo("You must specify an option (either --be or --bp) for the computation of the cumulative bitmap")
    except FileNotFoundError:
        click.echo("Device was not found. Possible issues: \n"
                   " - Are you sure you spelled it correctly?\n"
                   " - Are you in SRAM working directory? (tip: try \'sram_tools --sram-dir [DIRECTORY] ls\')"
                   "")
        exit(-1)

    bitmap /= len(devices)
    bitmap *= 255

    if res[0] * res[1] != bitmap.shape[0] * bitmap.shape[1]:
        raise Exception(
            "Invalid resolution! The total resolution must correspond to the total size of the SRAM memory,"
            " e.g 512 * 1536 = 96kB")

    im = Image.fromarray(bitmap.reshape(res[0], res[1]))
    im.show(title="Cumulative bitmap")


@bitmap.command()
@click.option('--be', '--bitmap_entropy', is_flag=True, help='Show a bitmap of the entropy the SRAM.')
@click.option('--bp', '--bitmap_probability', is_flag=True, help='Show a bitmap of the probability the SRAM.')
@click.option('-r', '--res', nargs=2, default=(768, 1024), help='Set resolution bitmap.')
@click.argument("devices", nargs=-1)
@pass_config
def simple(config, devices, bitmap_entropy, bitmap_probability, res):
    """ Generate a simple bitmap for one device. """
    for dev in devices:
        bitmap = None
        try:
            if bitmap_entropy:
                entropy_file = os.path.join(config.sram_dir, dev + ".dev", "entropy_map.npy")
                bitmap = numpy.load(entropy_file)
                logging.info("%s\t| Generating entropy bitmap", dev)
            elif bitmap_probability:
                probs_file = os.path.join(config.sram_dir, dev + ".dev", "probs_map.npy")
                bitmap = numpy.load(probs_file)
                logging.info("%s\t| Generating probability bitmap", dev)
            else:
                click.echo(
                    "You must either specify '--be' or '--bp' to generate a "
                    "bitmap based on the entropy per cell or cell probability.")
                exit(-1)
        except FileNotFoundError:
            click.echo("Device was not found. Possible issues: \n"
                       " - Are you sure you spelled it correctly?\n"
                       " - Are you in SRAM working directory? (tip: try \'sram_tools --sram-dir [DIRECTORY] ls\')"
                       "")
            exit(-1)

        bitmap *= 255

        if res[0] * res[1] != bitmap.shape[0] * bitmap.shape[1]:
            raise Exception(
                "Invalid resolution! The total resolution must correspond to the total size of the SRAM memory,"
                " e.g 512 * 1536 = 96kB")

        im = Image.fromarray(bitmap.reshape(res[0], res[1]))
        im.show(title=dev)


@cli.command()
@click.argument("devs", nargs=-1)
@pass_config
def hamming(config, devs):
    """ Calculate the average Hamming distance between two random SRAM prints of two devices or one device. """
    if len(devs) > 2:
        raise Exception("Too many arguments")

    elif len(devs) == 1:
        index1, index2 = -1, -1
        while index1 == index2:
            index1, index2 = randint(0, len(config.devices[devs[0]].sram_bin_maps) - 1), randint(0, len(
                config.devices[devs[0]].sram_bin_maps) - 1)

        file1 = os.path.join(config.sram_dir, devs[0] + ".dev", config.devices[devs[0]].sram_bin_maps[index1])
        file2 = os.path.join(config.sram_dir, devs[0] + ".dev", config.devices[devs[0]].sram_bin_maps[index2])

        bitmap1 = numpy.load(file1)
        bitmap2 = numpy.load(file2)

        total_hd = 0

        for l1, l2 in zip(bitmap1, bitmap2):
            total_hd += numpy.count_nonzero(l1 != l2)

        hd = total_hd / len(bitmap1)

        click.echo("Average Hamming distance per %d-bit line for device %s : %f" % (len(bitmap1[0]), devs[0], hd))

    elif len(devs) == 2:
        index1, index2 = -1, -1
        while index1 == index2:
            index1, index2 = randint(0, len(config.devices[devs[0]].sram_bin_maps) - 1), randint(0, len(
                config.devices[devs[1]].sram_bin_maps) - 1)

        file1 = os.path.join(config.sram_dir, devs[0] + ".dev", config.devices[devs[0]].sram_bin_maps[index1])
        file2 = os.path.join(config.sram_dir, devs[1] + ".dev", config.devices[devs[1]].sram_bin_maps[index2])

        bitmap1 = numpy.load(file1)
        bitmap2 = numpy.load(file2)

        total_hd = 0

        for l1, l2 in zip(bitmap1, bitmap2):
            total_hd += numpy.count_nonzero(l1 != l2)

        hd = total_hd / len(bitmap1)

        click.echo("Average Hamming distance per %d-bit line for devices %s - %s : %f" % (
            len(bitmap1[0]), devs[0], devs[1], hd))
    else:
        raise Exception("Too few arguments")


if __name__ == "__main__":
    cli()

