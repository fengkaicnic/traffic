from setuptools import find_packages
from setuptools import setup

from traffic.openstack.common.setup import get_cmdclass
from traffic.openstack.common.setup import parse_requirements
from traffic.openstack.common.setup import parse_dependency_links
from traffic.openstack.common.setup import write_requirements


requires = parse_requirements()
depend_links = parse_dependency_links()

write_requirements()

setup(name='traffic',
      version='2014.1',
      description="Traffic control for OpenStack",
      license='Apache License (2.0)',
      author='fk',
      author_email='fengkai@cnic.cn',
      url='http://www.openstack.org',
      cmdclass=get_cmdclass(),
      packages=find_packages(exclude=['test', 'bin']),
      include_package_data=True,
      scripts=['bin/traffic-api'],
      zip_safe=False,
      install_requires=requires,
      dependency_links=depend_links,
      test_suite='nose.collector',
      classifiers=[
          'Environment :: OpenStack',
          'Intended Audience :: Information Technology',
          'Intended Audience :: System Administrators',
          'License :: OSI Approved :: Apache Software License',
          'Operating System :: POSIX :: Linux',
          'Programming Language :: Python',
          'Programming Language :: Python :: 2',
          'Programming Language :: Python :: 2.7',
      ],
      )
                                                                                      