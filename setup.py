from setuptools import setup

setup(
    name='PPAW',
    version='0.0.0.dev',
    description='Python Poloniex API Wrapper',
    url='https://github.com/13steinj/python-poloniex',
    author='Jonathan Stein',
    author_email="13stein.j+pip@gmail.com",
    packages=['poloniex'],
    install_requires=['requests', 'six'],
)
