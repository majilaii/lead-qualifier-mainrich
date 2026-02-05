#!/bin/bash
# Lead Hunter - Quick Start Script
# Usage: ./run.sh [test|run|export|help] [--deep]

cd "$(dirname "$0")"
source venv/bin/activate

echo "🧲 THE MAGNET HUNTER - Mainrich International"
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
  deep)
    # Standalone deep research
    if [ -n "$2" ] && [ -n "$3" ]; then
      python deep_research.py "$2" "$3"
    else
      echo "Usage: ./run.sh deep 'Company Name' 'https://website.com'"
    fi
    ;;
  *)
    echo "Commands:"
    echo "  ./run.sh test              - Test with sample companies"
    echo "  ./run.sh test --deep       - Test with deep research on hot leads"
    echo "  ./run.sh run               - Process input_leads.csv"
    echo "  ./run.sh run --deep        - Process with deep research"
    echo "  ./run.sh export            - Export results to Excel"
    echo "  ./run.sh deep 'Name' 'URL' - Run deep research on one company"
    echo ""
    echo "Or use Python directly:"
    echo "  python main.py --help"
    ;;
esac
