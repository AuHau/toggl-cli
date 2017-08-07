from distutils.core import setup
setup(name='toggl-cli',
      version='0.0.1',
      description='A simple command-line interface for toggl.com',
      author='D. Robert Adams',
      author_email='d.robert.adams@gmail.com',
      url='http://github.com/drobertadams/toggl-cli/',
      requires=['iso8601', 'pytz', ' dateutil', 'requests'],
      scripts=['toggl.py', 'toggl.sh'],
      )
