# python-deps depends on
setuptools
# Usage
python main.py srcdir [extras]
# Usage
```
python3.9 main.py $SRCDIR dev test
```
# Examples
```
python3.9 main.py /usr/ports/net-im/py-matrix-synapse/work-py39/matrix_synapse-1.72.0/  matrix-synapse-ldap3
python3.9 main.py /usr/ports/devel/py-twisted/work-py39/Twisted-22.10.0/ tls test
```
prints metadata and the relevant runtime requirements for the package in $SRCDIR in the default_environment
specified in markes.py defalt_environment()
