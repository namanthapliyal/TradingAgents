"""TradingAgents: multi-agent LLM financial trading framework."""

__version__ = "0.6.0"

import warnings

from dotenv import find_dotenv, load_dotenv

# Suppress noisy pandas 2.2+ / 3.0+ deprecation warnings emitted by third-party vendor libraries (e.g. yfinance)
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", message=".*inplace.*")

# Load .env at package import so DEFAULT_CONFIG's env-var overlay and every LLM
# client see the user's keys whichever entry point started the process.
# usecwd=True walks from the working directory, so the installed console script
# finds the project's .env rather than looking beside site-packages. Values the
# caller has already exported are never overridden.
load_dotenv(find_dotenv(usecwd=True))
load_dotenv(find_dotenv(".env.enterprise", usecwd=True), override=False)
