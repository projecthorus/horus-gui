# This makefile has been created to help developers perform common actions.
# Most actions assume it is operating in a virtual environment where the
# python command links to the appropriate virtual environment Python.

# Do not remove this block. It is used by the 'help' rule when
# constructing the help output.
# help:
# help: horusgui Makefile help
# help:


# help: help                           - display this makefile's help information
.PHONY: help
help:
	@grep "^# help\:" Makefile | grep -v grep | sed 's/\# help\: //' | sed 's/\# help\://'


# help: style.check                    - perform code format compliance check
.PHONY: style.check
style.check:
	@black src/horusgui apps setup.py --check


# help: style                          - perform code format compliance changes
.PHONY: style
style:
	@black src/horusgui apps setup.py


# help: test                           - run tests
.PHONY: test
test:
	@python -m unittest discover -s tests


# help: test-verbose                   - run tests [verbosely]
.PHONY: test-verbose
test-verbose:
	@python -m unittest discover -s tests -v


# help: dist                           - create a wheel distribution package
.PHONY: dist
dist:
	@python setup.py bdist_wheel


# help: dist-upload                    - upload a wheel distribution package
.PHONY: dist-upload
dist-upload: dist
	@twine upload dist/spew-*-py3-none-any.whl


# Keep these lines at the end of the file to retain nice help
# output formatting.
# help:
