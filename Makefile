.PHONY: test doctor demo report docs api board clean

test:
	python3 -m unittest discover -s tests

doctor:
	python3 -m fantasyedge doctor

# End-to-end run with no credentials, against the bundled fixture.
demo:
	python3 -m fantasyedge --db data/demo.db pull --provider manual \
		--draft tests/fixtures/draft.txt --standings tests/fixtures/standings.txt \
		--league demo --season 2025
	python3 -m fantasyedge --db data/demo.db analyze

report:
	python3 -m fantasyedge report --out report.html

# The read API plus the mosaic. --host 0.0.0.0 lets a TV or headset reach it.
api:
	python3 -m fantasyedge api --host 0.0.0.0

board:
	python3 -m fantasyedge api

# Static build for GitHub Pages. --anon scrubs league and manager names.
docs:
	python3 tools/build_docs.py --anon

fixtures:
	python3 tests/fixtures/make_fixtures.py

clean:
	rm -rf data/*.db report.html
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
