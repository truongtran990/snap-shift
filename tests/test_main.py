import runpy
from unittest.mock import patch


def test_main_entry_point():
    """Test the main entry point"""
    with patch("amtt.cli.commands.cli") as mock_cli:
        # Import the module
        import amtt.__main__

        # Call the main function directly
        amtt.__main__.cli()

        # Verify cli() was called
        mock_cli.assert_called_once()


def test_main_module_execution():
    """Test execution as __main__"""
    with patch("amtt.cli.commands.cli") as mock_cli:
        # Run the module as __main__
        runpy.run_module("amtt.__main__", run_name="__main__")

        # Verify cli() was called
        mock_cli.assert_called_once()
