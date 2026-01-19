from setuptools import find_packages, setup

setup(
    name="gui-agents",
    version="0.4.0",
    description="A library for creating general purpose GUI agents using multimodal LLMs.",
    long_description=open("README.md", encoding="utf-8").read(),
    long_description_content_type="text/markdown",
    author="Simular AI",
    author_email="eric@simular.ai",
    packages=find_packages(),
    package_data={
        "gui_agents.s3.voice": ["assets/*.html"],
    },
    include_package_data=True,
    install_requires=[
        # Core dependencies
        "numpy",
        "backoff",
        "pandas",
        "openai",
        "anthropic",
        "fastapi",
        "uvicorn",
        "paddleocr",
        "paddlepaddle",
        "together",
        "scikit-learn",
        "websockets",
        "tiktoken",
        "selenium",
        "pyautogui",
        "toml",
        "pytesseract",
        "google-genai",
        "python-dotenv",
        "Pillow",
        # Recording dependencies
        "pynput>=1.7.6",
        "mss>=9.0.0",
        "opencv-python>=4.8.0",
        # Voice assistant dependencies
        "openwakeword>=0.6.0",
        "pyaudio>=0.2.13",
        "PyQt5>=5.15.0",
        "PyQtWebEngine>=5.15.0",
        # Platform-specific dependencies
        'pyobjc; platform_system == "Darwin"',
        'pyobjc-framework-Cocoa>=10.0; platform_system == "Darwin"',
        'pywinauto; platform_system == "Windows"',
        'pywin32; platform_system == "Windows"',
    ],
    extras_require={
        "dev": ["black"],
    },
    entry_points={
        "console_scripts": [
            "agent_s=gui_agents.s3.cli.main:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: Microsoft :: Windows",
        "Operating System :: POSIX :: Linux",
        "Operating System :: MacOS :: MacOS X",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    keywords="ai, llm, gui, agent, multimodal, voice, recording",
    project_urls={
        "Source": "https://github.com/simular-ai/Agent-S",
        "Bug Reports": "https://github.com/simular-ai/Agent-S/issues",
    },
    python_requires=">=3.9, <3.13",
)
