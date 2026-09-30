import os
from glob import glob

from setuptools import find_packages, setup

package_name = "anytraverse_ros"

setup(
    name=package_name,
    version="0.0.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="sattwik-sahu",
    maintainer_email="sattwik21@iiserb.ac.in",
    description="AnyTraverse ROS2 wrapper package",
    license="Apache-2.0",
    extras_require={
        "test": [
            "pytest",
        ],
    },
    entry_points={
        "console_scripts": ["anytraverse_node = anytraverse_ros.anytraverse_node:main"],
    },
)
