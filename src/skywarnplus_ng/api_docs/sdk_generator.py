"""
SDK generator for SkywarnPlus-NG API.
"""

import json
from typing import Dict, Any, List, Optional
from pathlib import Path
from jinja2 import Environment, FileSystemLoader


class SDKGenerator:
    """Generate SDK client libraries for SkywarnPlus-NG API."""
    
    def __init__(self, base_url: str = "http://localhost:8080", version: str = "2.0.0"):
        self.base_url = base_url
        self.version = version
        self.template_env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"))
    
    def generate_python_sdk(self) -> str:
        """Generate Python SDK."""
        template = self.template_env.get_template("python_sdk.py")
        
        return template.render(
            base_url=self.base_url,
            version=self.version
        )
    
    def generate_javascript_sdk(self) -> str:
        """Generate JavaScript/Node.js SDK."""
        template = self.template_env.get_template("javascript_sdk.js")
        
        return template.render(
            base_url=self.base_url,
            version=self.version
        )
    
    def generate_typescript_sdk(self) -> str:
        """Generate TypeScript SDK."""
        template = self.template_env.get_template("typescript_sdk.ts")
        
        return template.render(
            base_url=self.base_url,
            version=self.version
        )
    
    def generate_go_sdk(self) -> str:
        """Generate Go SDK."""
        template = self.template_env.get_template("go_sdk.go")
        
        return template.render(
            base_url=self.base_url,
            version=self.version
        )
    
    def generate_rust_sdk(self) -> str:
        """Generate Rust SDK."""
        template = self.template_env.get_template("rust_sdk.rs")
        
        return template.render(
            base_url=self.base_url,
            version=self.version
        )
    
    def generate_sdk_package_json(self) -> str:
        """Generate package.json for JavaScript SDK."""
        package_data = {
            "name": "skywarnplus-ng-sdk",
            "version": self.version,
            "description": "Official JavaScript SDK for SkywarnPlus-NG API",
            "main": "index.js",
            "types": "index.d.ts",
            "scripts": {
                "test": "jest",
                "build": "tsc",
                "prepublishOnly": "npm run build"
            },
            "keywords": [
                "weather",
                "alerts",
                "api",
                "sdk",
                "skywarnplus"
            ],
            "author": "SkywarnPlus-NG Team",
            "license": "MIT",
            "dependencies": {
                "axios": "^1.6.0"
            },
            "devDependencies": {
                "@types/node": "^20.0.0",
                "typescript": "^5.0.0",
                "jest": "^29.0.0"
            },
            "repository": {
                "type": "git",
                "url": "https://github.com/skywarnplus-ng/sdk-js.git"
            },
            "bugs": {
                "url": "https://github.com/skywarnplus-ng/sdk-js/issues"
            },
            "homepage": "https://github.com/skywarnplus-ng/sdk-js#readme"
        }
        
        return json.dumps(package_data, indent=2)
    
    def generate_python_setup_py(self) -> str:
        """Generate setup.py for Python SDK."""
        template = self.template_env.get_template("setup.py")
        
        return template.render(
            version=self.version
        )
    
    def generate_python_requirements_txt(self) -> str:
        """Generate requirements.txt for Python SDK."""
        return """requests>=2.31.0
websockets>=11.0.0
pydantic>=2.0.0
"""
    
    def generate_go_mod(self) -> str:
        """Generate go.mod for Go SDK."""
        return f"""module github.com/skywarnplus-ng/sdk-go

go 1.21

require (
    github.com/gorilla/websocket v1.5.0
)
"""
    
    def generate_cargo_toml(self) -> str:
        """Generate Cargo.toml for Rust SDK."""
        return f"""[package]
name = "skywarnplus-ng-sdk"
version = "{self.version}"
edition = "2021"
description = "Official Rust SDK for SkywarnPlus-NG API"
license = "MIT"
repository = "https://github.com/skywarnplus-ng/sdk-rust"
homepage = "https://github.com/skywarnplus-ng/sdk-rust"
documentation = "https://docs.rs/skywarnplus-ng-sdk"

[dependencies]
reqwest = {{ version = "0.11", features = ["json"] }}
tokio = {{ version = "1.0", features = ["full"] }}
serde = {{ version = "1.0", features = ["derive"] }}
serde_json = "1.0"
url = "2.4"
thiserror = "1.0"
"""
    
    def generate_sdk_readme(self, language: str) -> str:
        """Generate README for SDK."""
        template = self.template_env.get_template(f"{language}_sdk_readme.md")
        
        return template.render(
            base_url=self.base_url,
            version=self.version,
            language=language
        )
    
    def generate_sdk_tests(self, language: str) -> str:
        """Generate test files for SDK."""
        template = self.template_env.get_template(f"{language}_sdk_tests.{self._get_test_extension(language)}")
        
        return template.render(
            base_url=self.base_url,
            version=self.version
        )
    
    def _get_test_extension(self, language: str) -> str:
        """Get test file extension for language."""
        extensions = {
            "python": "py",
            "javascript": "js",
            "typescript": "ts",
            "go": "go",
            "rust": "rs"
        }
        return extensions.get(language, "txt")
    
    def generate_all_sdks(self, output_dir: Path) -> None:
        """Generate all SDKs to output directory."""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Python SDK
        python_dir = output_dir / "python"
        python_dir.mkdir(exist_ok=True)
        
        with open(python_dir / "skywarnplus_ng.py", 'w') as f:
            f.write(self.generate_python_sdk())
        
        with open(python_dir / "setup.py", 'w') as f:
            f.write(self.generate_python_setup_py())
        
        with open(python_dir / "requirements.txt", 'w') as f:
            f.write(self.generate_python_requirements_txt())
        
        with open(python_dir / "README.md", 'w') as f:
            f.write(self.generate_sdk_readme("python"))
        
        with open(python_dir / "test_sdk.py", 'w') as f:
            f.write(self.generate_sdk_tests("python"))
        
        # JavaScript SDK
        js_dir = output_dir / "javascript"
        js_dir.mkdir(exist_ok=True)
        
        with open(js_dir / "index.js", 'w') as f:
            f.write(self.generate_javascript_sdk())
        
        with open(js_dir / "package.json", 'w') as f:
            f.write(self.generate_sdk_package_json())
        
        with open(js_dir / "README.md", 'w') as f:
            f.write(self.generate_sdk_readme("javascript"))
        
        with open(js_dir / "test.js", 'w') as f:
            f.write(self.generate_sdk_tests("javascript"))
        
        # TypeScript SDK
        ts_dir = output_dir / "typescript"
        ts_dir.mkdir(exist_ok=True)
        
        with open(ts_dir / "index.ts", 'w') as f:
            f.write(self.generate_typescript_sdk())
        
        with open(ts_dir / "package.json", 'w') as f:
            f.write(self.generate_sdk_package_json())
        
        with open(ts_dir / "README.md", 'w') as f:
            f.write(self.generate_sdk_readme("typescript"))
        
        with open(ts_dir / "test.ts", 'w') as f:
            f.write(self.generate_sdk_tests("typescript"))
        
        # Go SDK
        go_dir = output_dir / "go"
        go_dir.mkdir(exist_ok=True)
        
        with open(go_dir / "skywarnplus.go", 'w') as f:
            f.write(self.generate_go_sdk())
        
        with open(go_dir / "go.mod", 'w') as f:
            f.write(self.generate_go_mod())
        
        with open(go_dir / "README.md", 'w') as f:
            f.write(self.generate_sdk_readme("go"))
        
        with open(go_dir / "skywarnplus_test.go", 'w') as f:
            f.write(self.generate_sdk_tests("go"))
        
        # Rust SDK
        rust_dir = output_dir / "rust"
        rust_dir.mkdir(exist_ok=True)
        
        with open(rust_dir / "src" / "lib.rs", 'w') as f:
            (rust_dir / "src").mkdir(exist_ok=True)
            f.write(self.generate_rust_sdk())
        
        with open(rust_dir / "Cargo.toml", 'w') as f:
            f.write(self.generate_cargo_toml())
        
        with open(rust_dir / "README.md", 'w') as f:
            f.write(self.generate_sdk_readme("rust"))
        
        with open(rust_dir / "tests" / "integration_test.rs", 'w') as f:
            (rust_dir / "tests").mkdir(exist_ok=True)
            f.write(self.generate_sdk_tests("rust"))
