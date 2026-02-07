#!/bin/bash
# ╔═══════════════════════════════════════════════╗
# ║  🧲 The Magnet Hunter — Quick Start Script    ║
# ║  Usage: ./run.sh [command] [options]           ║
# ╚═══════════════════════════════════════════════╝

cd "$(dirname "$0")"

# Activate virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
elif [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "❌ No virtual environment found. Run: python -m venv venv && pip install -r requirements.txt"
    exit 1
fi

echo "🧲 THE MAGNET HUNTER"
echo ""

case "$1" in
  test)
    if [ "$2" = "--deep" ]; then
      echo "Running test with deep research..."
      python main.py --test --clear-checkpoint --deep-research
    else
      echo "Running test..."
      python main.py --test --clear-checkpoint
    fi
    ;;
  run)
    if [ "$2" = "--deep" ]; then
      echo "Processing leads with deep research..."
      python main.py --deep-research
    else
      echo "Processing leads..."
      python main.py
    fi
    ;;
  export)
    python export.py excel
    ;;
  discover)
    echo "Discovering leads via Exa AI..."
    python test_exa.py --export
    ;;
  deep)
    # Standalone deep research on a single company
    if [ -n "$2" ] && [ -n "$3" ]; then
      python deep_research.py "$2" "$3"
    else
      echo "Usage: ./run.sh deep 'Company Name' 'https://website.com'"
      echo "Example: ./run.sh deep 'Maxon Group' 'https://www.maxongroup.com'"
    fi
    ;;
  *)
    echo "Usage: ./run.sh [command] [options]"
    echo ""
    echo "Commands:"
    echo "  test              Test with 4 sample companies"
    echo "  test --deep       Test + deep research on hot leads"
    echo "  run               Process input_leads.csv"
    echo "  run --deep        Process + deep research on hot leads"
    echo "  discover          Find leads via Exa AI (requires EXA_API_KEY)"
    echo "  export            Export results to Excel (.xlsx)"
    echo "  deep NAME URL     Deep research on one company"
    echo ""
    echo "Or use Python directly:"
    echo "  python main.py --help"
    echo "  python test_exa.py --help"
    ;;
esac
