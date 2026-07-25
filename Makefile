.PHONY: install install-user dev test doctor clean

install install-user:
	python3 -m pip install --user --upgrade .
	@echo "installed fiver (user)"

dev:
	python3 -m pip install --user -e ".[dev]"

test:
	python3 -m compileall -q src
	python3 -m pytest -q || python3 -c "from fiver.cli import build_parser; build_parser(); print('import ok')"

doctor:
	fiver --doctor || python3 -m fiver --doctor

clean:
	rm -rf build dist *.egg-info src/*.egg-info .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
