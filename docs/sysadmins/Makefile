# Makefile for generating architecture diagrams
# Run 'make' or 'make all' to generate all diagrams
# Run 'make clean' to remove generated images

# Python interpreter
PYTHON := python3

# Output image files
IMAGES := overall_architecture.png tsimsh_architecture.png wsgi_architecture.png

# Default target - generate all images
.PHONY: all
all: $(IMAGES)

# Generate overall system architecture diagram
overall_architecture.png: generate_overall_architecture.py
	@echo "Generating overall system architecture diagram..."
	@$(PYTHON) generate_overall_architecture.py
	@echo "✓ Overall architecture diagram created: $@"

# Generate tsimsh CLI architecture diagram
tsimsh_architecture.png: generate_tsimsh_architecture.py
	@echo "Generating tsimsh CLI architecture diagram..."
	@$(PYTHON) generate_tsimsh_architecture.py
	@echo "✓ tsimsh architecture diagram created: $@"

# Generate WSGI web interface architecture diagram
wsgi_architecture.png: generate_wsgi_architecture.py
	@echo "Generating WSGI web interface architecture diagram..."
	@$(PYTHON) generate_wsgi_architecture.py
	@echo "✓ WSGI architecture diagram created: $@"

# Individual targets for specific diagrams
.PHONY: overall
overall: overall_architecture.png

.PHONY: tsimsh
tsimsh: tsimsh_architecture.png

.PHONY: wsgi
wsgi: wsgi_architecture.png

# Clean generated images
.PHONY: clean
clean:
	@echo "Removing generated architecture diagrams..."
	@rm -f $(IMAGES)
	@echo "✓ Cleaned up generated images"

# View generated images (requires an image viewer)
.PHONY: view
view: all
	@echo "Opening generated images..."
	@for img in $(IMAGES); do \
		if [ -f $$img ]; then \
			echo "Opening $$img..."; \
			xdg-open $$img 2>/dev/null || open $$img 2>/dev/null || echo "Please open $$img manually"; \
		fi \
	done

# Check dependencies
.PHONY: check-deps
check-deps:
	@echo "Checking Python dependencies..."
	@$(PYTHON) -c "import matplotlib" 2>/dev/null || (echo "❌ matplotlib not installed. Run: pip install matplotlib" && exit 1)
	@echo "✓ All dependencies satisfied"

# Help target
.PHONY: help
help:
	@echo "Traceroute Simulator - Architecture Diagram Generator"
	@echo ""
	@echo "Usage:"
	@echo "  make              - Generate all architecture diagrams"
	@echo "  make all          - Generate all architecture diagrams"
	@echo "  make overall      - Generate overall system architecture diagram"
	@echo "  make tsimsh       - Generate tsimsh CLI architecture diagram"
	@echo "  make wsgi         - Generate WSGI web interface architecture diagram"
	@echo "  make clean        - Remove all generated images"
	@echo "  make view         - Generate and view all diagrams"
	@echo "  make check-deps   - Check if required Python packages are installed"
	@echo "  make help         - Show this help message"
	@echo ""
	@echo "Generated files:"
	@echo "  overall_architecture.png - System-wide architecture overview"
	@echo "  tsimsh_architecture.png  - Command-line interface architecture"
	@echo "  wsgi_architecture.png    - Web interface architecture"

# Prevent deletion of intermediate files
.PRECIOUS: %.png

# Silent mode for Python scripts (no matplotlib window)
export MPLBACKEND := Agg