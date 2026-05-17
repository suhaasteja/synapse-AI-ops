.PHONY: install list-scenarios validate recommend-all validate-all demo eval

install:
	pip install -r requirements.txt

list-scenarios:
	python -m src.cli list-scenarios

validate:
	@set -e; \
	found=0; \
	for f in output/*.json; do \
		if [ -f "$$f" ]; then \
			found=1; \
			python ../ai_factory_hackathon_student/validate_recommendation.py "$$f"; \
		fi; \
	done; \
	if [ $$found -eq 0 ]; then \
		echo "No JSON files found in output/"; \
		exit 1; \
	fi

recommend-all:
	python -m src.cli recommend-all --no-llm

validate-all:
	python ../ai_factory_hackathon_student/validate_recommendation.py --require-all output/all.json

demo:
	python -m src.cli recommend-all --no-llm && python -m src.cli ui

eval:
	python -m src.cli eval-agents
