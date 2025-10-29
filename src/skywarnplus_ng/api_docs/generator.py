"""
Comprehensive API documentation generator for SkywarnPlus-NG.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from .openapi import OpenAPIGenerator
from .interactive_docs import InteractiveDocsGenerator
from .code_examples import CodeExampleGenerator
from .sdk_generator import SDKGenerator
from .postman import PostmanCollectionGenerator


class APIDocumentationGenerator:
    """Generate comprehensive API documentation for SkywarnPlus-NG."""
    
    def __init__(self, base_url: str = "http://localhost:8080", version: str = "2.0.0"):
        self.base_url = base_url
        self.version = version
        
        # Initialize generators
        self.openapi_generator = OpenAPIGenerator(base_url, version)
        self.interactive_generator = InteractiveDocsGenerator(base_url, version)
        self.code_examples_generator = CodeExampleGenerator(base_url)
        self.sdk_generator = SDKGenerator(base_url, version)
        self.postman_generator = PostmanCollectionGenerator(base_url, version)
    
    def generate_all_documentation(self, output_dir: Path) -> None:
        """Generate all API documentation."""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"Generating API documentation for SkywarnPlus-NG v{self.version}")
        print(f"Base URL: {self.base_url}")
        print(f"Output directory: {output_dir}")
        
        # Generate OpenAPI specification
        print("Generating OpenAPI specification...")
        self.openapi_generator.save_spec(str(output_dir / "openapi.json"))
        
        # Save YAML spec
        yaml_spec = self.openapi_generator.get_yaml_spec()
        with open(output_dir / "openapi.yaml", 'w', encoding='utf-8') as f:
            f.write(yaml_spec)
        
        # Generate interactive documentation
        print("Generating interactive documentation...")
        self.interactive_generator.save_docs(output_dir / "interactive")
        
        # Generate API reference
        print("Generating API reference...")
        api_reference = self.interactive_generator.generate_api_reference()
        with open(output_dir / "api_reference.md", 'w', encoding='utf-8') as f:
            f.write(api_reference)
        
        # Generate quickstart guide
        print("Generating quickstart guide...")
        quickstart_guide = self.interactive_generator.generate_quickstart_guide()
        with open(output_dir / "quickstart_guide.md", 'w', encoding='utf-8') as f:
            f.write(quickstart_guide)
        
        # Generate code examples
        print("Generating code examples...")
        self._generate_code_examples(output_dir)
        
        # Generate SDKs
        print("Generating SDKs...")
        self.sdk_generator.generate_all_sdks(output_dir / "sdks")
        
        # Generate Postman collection
        print("Generating Postman collection...")
        self.postman_generator.save_collection(str(output_dir / "skywarnplus-ng-api.postman_collection.json"))
        self.postman_generator.save_environment(str(output_dir / "skywarnplus-ng-environment.postman_environment.json"))
        
        # Generate main documentation index
        print("Generating documentation index...")
        self._generate_documentation_index(output_dir)
        
        print("✅ API documentation generation complete!")
        print(f"📁 Documentation available at: {output_dir}")
        print(f"🌐 Interactive docs: {output_dir / 'interactive' / 'swagger.html'}")
        print(f"📚 API reference: {output_dir / 'api_reference.md'}")
        print(f"🚀 Quickstart guide: {output_dir / 'quickstart_guide.md'}")
        print(f"💻 SDKs: {output_dir / 'sdks'}")
        print(f"📮 Postman collection: {output_dir / 'skywarnplus-ng-api.postman_collection.json'}")
    
    def _generate_code_examples(self, output_dir: Path) -> None:
        """Generate code examples in multiple languages."""
        examples_dir = output_dir / "examples"
        examples_dir.mkdir(exist_ok=True)
        
        # Generate all examples
        all_examples = self.code_examples_generator.generate_all_examples()
        
        for language, examples in all_examples.items():
            lang_dir = examples_dir / language
            lang_dir.mkdir(exist_ok=True)
            
            # Generate individual example files
            for example in examples:
                filename = f"{example.title.lower().replace(' ', '_').replace('(', '').replace(')', '')}.{self._get_file_extension(language)}"
                filepath = lang_dir / filename
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(f"# {example.title}\n\n")
                    f.write(f"{example.description}\n\n")
                    f.write(f"**Endpoint:** `{example.method} {example.endpoint}`\n\n")
                    f.write(f"```{language}\n{example.code}\n```\n")
            
            # Generate combined examples file
            combined_file = lang_dir / f"all_examples.{self._get_file_extension(language)}"
            with open(combined_file, 'w', encoding='utf-8') as f:
                f.write(f"# SkywarnPlus-NG API Examples - {language.title()}\n\n")
                f.write(f"Complete collection of API examples for SkywarnPlus-NG.\n\n")
                f.write(f"Base URL: {self.base_url}\n")
                f.write(f"API Version: {self.version}\n\n")
                
                for example in examples:
                    f.write(f"## {example.title}\n\n")
                    f.write(f"{example.description}\n\n")
                    f.write(f"**Endpoint:** `{example.method} {example.endpoint}`\n\n")
                    f.write(f"```{language}\n{example.code}\n```\n\n")
        
        # Generate README for examples
        readme_content = self._generate_examples_readme(all_examples)
        with open(examples_dir / "README.md", 'w', encoding='utf-8') as f:
            f.write(readme_content)
    
    def _get_file_extension(self, language: str) -> str:
        """Get file extension for language."""
        extensions = {
            "python": "py",
            "javascript": "js",
            "curl": "sh"
        }
        return extensions.get(language, "txt")
    
    def _generate_examples_readme(self, all_examples: Dict[str, Any]) -> str:
        """Generate README for examples directory."""
        return f"""# SkywarnPlus-NG API Examples

This directory contains code examples for the SkywarnPlus-NG API in multiple programming languages.

## Available Languages

{chr(10).join([f"- **{lang.title()}** - {len(examples)} examples" for lang, examples in all_examples.items()])}

## Quick Start

1. Choose your preferred language directory
2. Copy the example code
3. Modify the base URL and parameters as needed
4. Run the examples

## Base URL

```
{self.base_url}
```

## API Version

{self.version}

## Examples by Language

{chr(10).join([f"### {lang.title()}\n\n{chr(10).join([f"- [{example.title}]({lang}/{example.title.lower().replace(' ', '_').replace('(', '').replace(')', '')}.{self._get_file_extension(lang)})" for example in examples])}\n" for lang, examples in all_examples.items()])}

## Getting Help

- [Full API Reference](../api_reference.md)
- [Quickstart Guide](../quickstart_guide.md)
- [Interactive Documentation](../interactive/swagger.html)
- [GitHub Repository](https://github.com/skywarnplus-ng/skywarnplus-ng)

---

**Generated on:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
    
    def _generate_documentation_index(self, output_dir: Path) -> None:
        """Generate main documentation index."""
        index_content = f"""# SkywarnPlus-NG API Documentation

Welcome to the comprehensive API documentation for SkywarnPlus-NG, the professional weather alert monitoring and notification system.

## 📚 Documentation Overview

This documentation provides everything you need to integrate with the SkywarnPlus-NG API:

- **Interactive Documentation** - Try the API directly in your browser
- **API Reference** - Complete endpoint documentation
- **Quickstart Guide** - Get up and running in minutes
- **Code Examples** - Real code samples in multiple languages
- **SDKs** - Official client libraries
- **Postman Collection** - Ready-to-import API collection

## 🚀 Quick Links

| Resource | Description | Link |
|----------|-------------|------|
| **Interactive Docs** | Try the API in your browser | [Swagger UI](interactive/swagger.html) |
| **API Reference** | Complete endpoint documentation | [api_reference.md](api_reference.md) |
| **Quickstart Guide** | Get started quickly | [quickstart_guide.md](quickstart_guide.md) |
| **Code Examples** | Real code samples | [examples/](examples/) |
| **Python SDK** | Official Python client | [sdks/python/](sdks/python/) |
| **JavaScript SDK** | Official JavaScript client | [sdks/javascript/](sdks/javascript/) |
| **TypeScript SDK** | Official TypeScript client | [sdks/typescript/](sdks/typescript/) |
| **Go SDK** | Official Go client | [sdks/go/](sdks/go/) |
| **Rust SDK** | Official Rust client | [sdks/rust/](sdks/rust/) |
| **Postman Collection** | Import into Postman | [skywarnplus-ng-api.postman_collection.json](skywarnplus-ng-api.postman_collection.json) |

## 🔧 API Information

- **Base URL:** `{self.base_url}`
- **Version:** {self.version}
- **Protocol:** HTTP/HTTPS
- **Format:** JSON
- **Authentication:** None (currently)

## 📖 Getting Started

1. **Read the Quickstart Guide** - [quickstart_guide.md](quickstart_guide.md)
2. **Try the Interactive Docs** - [interactive/swagger.html](interactive/swagger.html)
3. **Choose your SDK** - [sdks/](sdks/)
4. **Import Postman Collection** - [skywarnplus-ng-api.postman_collection.json](skywarnplus-ng-api.postman_collection.json)

## 🌟 Key Features

- **Real-time Weather Alerts** - Get live weather alerts from the National Weather Service
- **Multi-channel Notifications** - Email, webhooks, and push notifications
- **Subscriber Management** - Manage notification preferences and geographic filtering
- **Template System** - Customizable notification templates
- **WebSocket Support** - Real-time updates via WebSocket
- **Comprehensive Monitoring** - Health checks, metrics, and logging
- **Configuration Management** - Full API-based configuration

## 📊 API Endpoints

### Core Endpoints
- `GET /api/status` - System status
- `GET /api/health` - System health
- `GET /api/alerts` - Active weather alerts
- `GET /api/alerts/history` - Alert history

### Configuration
- `GET /api/config` - Get configuration
- `POST /api/config` - Update configuration
- `POST /api/config/reset` - Reset to defaults

### Notifications
- `GET /api/notifications/subscribers` - List subscribers
- `POST /api/notifications/subscribers` - Add subscriber
- `GET /api/notifications/templates` - List templates
- `POST /api/notifications/test-email` - Test email connection

### Monitoring
- `GET /api/logs` - System logs
- `GET /api/metrics` - System metrics
- `GET /api/database/stats` - Database statistics

### Real-time
- `GET /ws` - WebSocket connection

## 💻 Code Examples

### Python
```python
from skywarnplus_ng import SkywarnPlusClient

client = SkywarnPlusClient('{self.base_url}')
status = client.get_status()
alerts = client.get_alerts()
```

### JavaScript
```javascript
const SkywarnPlus = require('skywarnplus-ng-sdk');

const client = new SkywarnPlus.Client('{self.base_url}');
const status = await client.getStatus();
const alerts = await client.getAlerts();
```

### cURL
```bash
# Get system status
curl {self.base_url}/api/status

# Get active alerts
curl {self.base_url}/api/alerts
```

## 🔗 Resources

- **GitHub Repository:** [skywarnplus-ng/skywarnplus-ng](https://github.com/skywarnplus-ng/skywarnplus-ng)
- **Issues & Support:** [GitHub Issues](https://github.com/skywarnplus-ng/skywarnplus-ng/issues)
- **License:** MIT

## 📝 Changelog

### Version {self.version}
- Initial API documentation release
- Complete OpenAPI 3.0 specification
- Interactive documentation with Swagger UI
- Official SDKs for Python, JavaScript, TypeScript, Go, and Rust
- Postman collection for API testing
- Comprehensive code examples

---

**Generated on:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}  
**API Version:** {self.version}  
**Base URL:** {self.base_url}
"""
        
        with open(output_dir / "README.md", 'w', encoding='utf-8') as f:
            f.write(index_content)
    
    def generate_web_docs_endpoint(self) -> str:
        """Generate HTML for web dashboard docs endpoint."""
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SkywarnPlus-NG API Documentation</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f8fafc;
            color: #1f2937;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }}
        .header {{
            background: linear-gradient(135deg, #1f2937 0%, #374151 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        .header h1 {{
            margin: 0 0 10px 0;
            font-size: 2.5rem;
            font-weight: 700;
        }}
        .header p {{
            margin: 0;
            font-size: 1.2rem;
            opacity: 0.9;
        }}
        .content {{
            padding: 40px;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 40px;
        }}
        .card {{
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 20px;
            transition: all 0.2s;
        }}
        .card:hover {{
            border-color: #3b82f6;
            box-shadow: 0 4px 12px rgba(59, 130, 246, 0.15);
        }}
        .card h3 {{
            margin: 0 0 10px 0;
            color: #1f2937;
            font-size: 1.25rem;
        }}
        .card p {{
            margin: 0 0 15px 0;
            color: #6b7280;
            line-height: 1.5;
        }}
        .card a {{
            color: #3b82f6;
            text-decoration: none;
            font-weight: 500;
        }}
        .card a:hover {{
            text-decoration: underline;
        }}
        .api-info {{
            background: #f3f4f6;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 30px;
        }}
        .api-info h3 {{
            margin: 0 0 15px 0;
            color: #1f2937;
        }}
        .api-info code {{
            background: #e5e7eb;
            padding: 2px 6px;
            border-radius: 4px;
            font-family: 'Monaco', 'Consolas', monospace;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>SkywarnPlus-NG API</h1>
            <p>Professional Weather Alert Monitoring & Notification System</p>
        </div>
        
        <div class="content">
            <div class="api-info">
                <h3>API Information</h3>
                <p><strong>Base URL:</strong> <code>{self.base_url}</code></p>
                <p><strong>Version:</strong> <code>{self.version}</code></p>
                <p><strong>Format:</strong> JSON</p>
                <p><strong>Authentication:</strong> None (currently)</p>
            </div>
            
            <div class="grid">
                <div class="card">
                    <h3>📖 Interactive Documentation</h3>
                    <p>Try the API directly in your browser with our interactive Swagger UI documentation.</p>
                    <a href="/docs/swagger" target="_blank">Open Swagger UI →</a>
                </div>
                
                <div class="card">
                    <h3>📚 API Reference</h3>
                    <p>Complete documentation of all API endpoints, request/response formats, and data models.</p>
                    <a href="/docs/api-reference" target="_blank">View API Reference →</a>
                </div>
                
                <div class="card">
                    <h3>🚀 Quickstart Guide</h3>
                    <p>Get up and running with the SkywarnPlus-NG API in just a few minutes.</p>
                    <a href="/docs/quickstart" target="_blank">Start Here →</a>
                </div>
                
                <div class="card">
                    <h3>💻 Code Examples</h3>
                    <p>Real code samples in Python, JavaScript, cURL, and more to help you get started quickly.</p>
                    <a href="/docs/examples" target="_blank">Browse Examples →</a>
                </div>
                
                <div class="card">
                    <h3>🔧 SDKs</h3>
                    <p>Official client libraries for Python, JavaScript, TypeScript, Go, and Rust.</p>
                    <a href="/docs/sdks" target="_blank">Download SDKs →</a>
                </div>
                
                <div class="card">
                    <h3>📮 Postman Collection</h3>
                    <p>Import our ready-to-use Postman collection to test the API in your favorite API client.</p>
                    <a href="/docs/postman" target="_blank">Get Collection →</a>
                </div>
            </div>
            
            <div style="text-align: center; margin-top: 40px; padding-top: 20px; border-top: 1px solid #e5e7eb;">
                <p style="color: #6b7280; margin: 0;">
                    Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')} | 
                    <a href="https://github.com/skywarnplus-ng/skywarnplus-ng" style="color: #3b82f6;">GitHub Repository</a>
                </p>
            </div>
        </div>
    </div>
</body>
</html>"""
