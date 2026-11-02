pycatia3dx
==========

alpha software
--------------

This is alpha software.

Please report any issues with using the package on github providing a stripped
down script.

Requirements
------------

* python >= 3.12
* **CATIA 3DExperience** running on Windows.
* see requirements.txt

Installation
------------

    python -m pip install pycatia3dx

Documentation
-------------

https://evereux.github.io/pycatia3dx-docs/


Examples And Scripts
--------------------

https://github.com/evereux/pycatia3dx/tree/main/examples


Asking Questions
----------------

Please read the following with regards to raising questions: https://github.com/evereux/pycatia/issues/28


Contributing
------------

See CONTRIBUTING.md in root of github repository.

Running The Tests
-----------------

CATIA 3DEXPERIENCE should already be running. Test files (3DPart, 3DShape, Drawing)
and geometry are verified or created automatically when running `pytest`, and
test fixtures work regardless of the CATIA interface language (English, French,
German, etc.). Documents you already have open are preserved and left untouched.

You can also run the file checker standalone:

.. code-block:: python

    python .\tests\check_test_files.py

To run the tests with coverage (-v is verbosity):

.. code-block:: python

    py.test -v --cov-report term-missing --cov=pycatia3dx

To run tests for a specific module

.. code-block:: python

    py.test -v tests/in/hybrid_shapes/test_hybrid_shape_factory.py

To stop tests running after first failure.

    py.test -vx




