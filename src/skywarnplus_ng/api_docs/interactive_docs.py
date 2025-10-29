"""
Interactive API documentation generator for SkywarnPlus-NG.
"""

import json
from typing import Dict, Any, List, Optional
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

from .openapi import OpenAPIGenerator


class InteractiveDocsGenerator:
    """Generate interactive API documentation using Swagger UI."""
    
    def __init__(self, base_url: str = "http://localhost:8080", version: str = "2.0.0"):
        self.base_url = base_url
        self.version = version
        self.openapi_generator = OpenAPIGenerator(base_url, version)
        self.template_env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"))
    
    def generate_docs_html(self) -> str:
        """Generate interactive documentation HTML."""
        template = self.template_env.get_template("swagger_ui.html")
        
        # Get OpenAPI spec
        openapi_spec = self.openapi_generator.generate_spec()
        
        return template.render(
            title="SkywarnPlus-NG API Documentation",
            openapi_spec=json.dumps(openapi_spec, indent=2),
            base_url=self.base_url,
            version=self.version
        )
    
    def generate_redoc_html(self) -> str:
        """Generate ReDoc documentation HTML."""
        template = self.template_env.get_template("redoc.html")
        
        # Get OpenAPI spec
        openapi_spec = self.openapi_generator.generate_spec()
        
        return template.render(
            title="SkywarnPlus-NG API Documentation",
            openapi_spec=json.dumps(openapi_spec, indent=2),
            base_url=self.base_url,
            version=self.version
        )
    
    def save_docs(self, output_dir: Path) -> None:
        """Save interactive documentation files."""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate Swagger UI
        swagger_html = self.generate_docs_html()
        with open(output_dir / "swagger.html", 'w', encoding='utf-8') as f:
            f.write(swagger_html)
        
        # Generate ReDoc
        redoc_html = self.generate_redoc_html()
        with open(output_dir / "redoc.html", 'w', encoding='utf-8') as f:
            f.write(redoc_html)
        
        # Save OpenAPI spec
        self.openapi_generator.save_spec(str(output_dir / "openapi.json"))
        
        # Save YAML spec
        yaml_spec = self.openapi_generator.get_yaml_spec()
        with open(output_dir / "openapi.yaml", 'w', encoding='utf-8') as f:
            f.write(yaml_spec)
    
    def generate_api_reference(self) -> str:
        """Generate markdown API reference."""
        template = self.template_env.get_template("api_reference.md")
        
        # Get OpenAPI spec
        openapi_spec = self.openapi_generator.generate_spec()
        
        return template.render(
            title="SkywarnPlus-NG API Reference",
            openapi_spec=openapi_spec,
            base_url=self.base_url,
            version=self.version
        )
    
    def generate_quickstart_guide(self) -> str:
        """Generate quickstart guide."""
        template = self.template_env.get_template("quickstart_guide.md")
        
        return template.render(
            title="SkywarnPlus-NG API Quickstart Guide",
            base_url=self.base_url,
            version=self.version
        )
    
    def generate_postman_collection(self) -> Dict[str, Any]:
        """Generate Postman collection."""
        from .postman import PostmanCollectionGenerator
        
        postman_generator = PostmanCollectionGenerator(self.base_url)
        return postman_generator.generate_collection()
    
    def generate_curl_examples(self) -> List[Dict[str, str]]:
        """Generate cURL examples for all endpoints."""
        examples = []
        
        # Status endpoint
        examples.append({
            "name": "Get System Status",
            "description": "Retrieve current system status",
            "method": "GET",
            "url": f"{self.base_url}/api/status",
            "curl": f"curl -X GET '{self.base_url}/api/status'"
        })
        
        # Alerts endpoint
        examples.append({
            "name": "Get Active Alerts",
            "description": "Retrieve currently active weather alerts",
            "method": "GET",
            "url": f"{self.base_url}/api/alerts",
            "curl": f"curl -X GET '{self.base_url}/api/alerts'"
        })
        
        # Alerts with filters
        examples.append({
            "name": "Get Alerts by County",
            "description": "Get alerts for a specific county",
            "method": "GET",
            "url": f"{self.base_url}/api/alerts?county=TXC039",
            "curl": f"curl -X GET '{self.base_url}/api/alerts?county=TXC039'"
        })
        
        # Health endpoint
        examples.append({
            "name": "Get System Health",
            "description": "Retrieve detailed system health information",
            "method": "GET",
            "url": f"{self.base_url}/api/health",
            "curl": f"curl -X GET '{self.base_url}/api/health'"
        })
        
        # Configuration endpoint
        examples.append({
            "name": "Get Configuration",
            "description": "Retrieve current system configuration",
            "method": "GET",
            "url": f"{self.base_url}/api/config",
            "curl": f"curl -X GET '{self.base_url}/api/config'"
        })
        
        # Update configuration
        examples.append({
            "name": "Update Configuration",
            "description": "Update system configuration",
            "method": "POST",
            "url": f"{self.base_url}/api/config",
            "curl": f"curl -X POST '{self.base_url}/api/config' \\\n  -H 'Content-Type: application/json' \\\n  -d '{{\"poll_interval\": 300}}'"
        })
        
        # Test email
        examples.append({
            "name": "Test Email Connection",
            "description": "Test email SMTP connection",
            "method": "POST",
            "url": f"{self.base_url}/api/notifications/test-email",
            "curl": f"curl -X POST '{self.base_url}/api/notifications/test-email' \\\n  -H 'Content-Type: application/json' \\\n  -d '{{\"provider\": \"gmail\", \"smtp_server\": \"smtp.gmail.com\", \"smtp_port\": 587, \"username\": \"your-email@gmail.com\", \"password\": \"your-app-password\"}}'"
        })
        
        # Get subscribers
        examples.append({
            "name": "Get Subscribers",
            "description": "Retrieve all notification subscribers",
            "method": "GET",
            "url": f"{self.base_url}/api/notifications/subscribers",
            "curl": f"curl -X GET '{self.base_url}/api/notifications/subscribers'"
        })
        
        # Add subscriber
        examples.append({
            "name": "Add Subscriber",
            "description": "Add a new notification subscriber",
            "method": "POST",
            "url": f"{self.base_url}/api/notifications/subscribers",
            "curl": f"curl -X POST '{self.base_url}/api/notifications/subscribers' \\\n  -H 'Content-Type: application/json' \\\n  -d '{{\"name\": \"John Doe\", \"email\": \"john@example.com\", \"preferences\": {{\"counties\": [\"TXC039\"], \"enabled_methods\": [\"email\"]}}}}'"
        })
        
        # Get templates
        examples.append({
            "name": "Get Templates",
            "description": "Retrieve all notification templates",
            "method": "GET",
            "url": f"{self.base_url}/api/notifications/templates",
            "curl": f"curl -X GET '{self.base_url}/api/notifications/templates'"
        })
        
        # Get metrics
        examples.append({
            "name": "Get Metrics",
            "description": "Retrieve system performance metrics",
            "method": "GET",
            "url": f"{self.base_url}/api/metrics",
            "curl": f"curl -X GET '{self.base_url}/api/metrics'"
        })
        
        # Get logs
        examples.append({
            "name": "Get Logs",
            "description": "Retrieve system logs",
            "method": "GET",
            "url": f"{self.base_url}/api/logs",
            "curl": f"curl -X GET '{self.base_url}/api/logs'"
        })
        
        return examples
