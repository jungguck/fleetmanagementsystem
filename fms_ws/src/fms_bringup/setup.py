import os
from glob import glob
from setuptools import find_packages, setup

package_name = 'fms_bringup'

setup(
    name=package_name,
    version='0.0.1',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
        (os.path.join('share', package_name, 'config'), glob('config/*')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='jungguck',
    maintainer_email='imguck1684@gmail.com',
    description='FMS TurtleBot Fleet bringup launch (P0-3 sim, P0-4 nav2)',
    license='MIT',
    tests_require=['pytest'],
    entry_points={'console_scripts': []},
)
