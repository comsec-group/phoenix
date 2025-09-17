import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

from pythondata_cpu_vexriscv_smp import version_str

setuptools.setup(
    name="pythondata-cpu-vexriscv-smp",
    version=version_str,
    author="LiteX Authors",
    author_email="litex@googlegroups.com",
    description="""\
Python module containing verilog files for VexRISCV SMP cpu.""",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/litex-hub/pythondata-cpu-vexriscv-smp",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.5',
    zip_safe=False,
    packages=setuptools.find_packages(),
    package_data={
    	'cpu_vexriscv_smp': ['cpu_vexriscv_smp/verilog/**'],
    },
    include_package_data=True,
    project_urls={
        "Bug Tracker": "https://github.com/litex-hub/pythondata-cpu-vexriscv-smp/issues",
        "Source Code": "https://github.com/litex-hub/pythondata-cpu-vexriscv-smp",
    },
)
