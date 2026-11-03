from pathlib import Path

from setuptools import find_packages, setup

HERE = Path(__file__).parent
long_description = (HERE / "README.md").read_text(encoding="utf-8")


def load_requirements(path: Path = HERE / 'requirements.txt'):
    """Load requirements from requirements.txt (ignore comments/empty lines)."""
    text = path.read_text(encoding='utf-8')
    lines = [ln.strip() for ln in text.splitlines()]
    return [ln for ln in lines if ln and not ln.startswith('#')]


setup(
    name="meroshare-bot",
    version="0.0.9",
    description="Meroshare IPO auto-apply bot",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Sudeep Das",
    packages=find_packages(),
    py_modules=["main"],
    include_package_data=True,
    package_data={
        "bot": ["demats.txt", "config.ini", "run_bot.bat", "install_playwright.bat"],
    },
    entry_points={
        "console_scripts": [
            "meroshare-bot=main:main",
        ],
    },
    install_requires=load_requirements(),
    python_requires=">=3.9",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: Microsoft :: Windows",
    ],
)
