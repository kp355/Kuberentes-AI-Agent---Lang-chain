from setuptools import setup, find_packages

setup(
    name="k8s-dashboard",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "fastapi>=0.68.0",
        "uvicorn>=0.15.0",
        "python-dotenv>=0.19.0",
        "pydantic>=1.8.0,<2.0.0",
        "python-dateutil>=2.8.2",
        "openai>=0.27.0",
    ],
)
