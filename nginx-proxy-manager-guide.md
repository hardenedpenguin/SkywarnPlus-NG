# Configuring Nginx Proxy Manager with SkywarnPlus-NG

This guide explains how to configure Nginx Proxy Manager (NPM) to reverse proxy SkywarnPlus-NG on your AllStarLink node, allowing you to access it via HTTPS at a custom subpath.

## Prerequisites

- SkywarnPlus-NG installed and running on your ASL3 node (default port 8100)
- Nginx Proxy Manager installed and configured
- An existing Proxy Host in NPM with SSL configured
- Your ASL node accessible from your NPM instance

## Verify SkywarnPlus-NG is Running

Before configuring NPM, verify that SkywarnPlus-NG is running and accessible locally:

```bash
# Check service status
sudo systemctl status skywarnplus-ng

# Verify it's listening on port 8100
sudo ss -tulpn | grep 8100

# Test local access
curl http://127.0.0.1:8100
```

You should see HTML output from the curl command if the service is running correctly.

## Configuration

This configuration allows you to access SkywarnPlus-NG at a subpath like `https://yourdomain.com/skywarnplus-ng`

**In Nginx Proxy Manager:**

1. Navigate to your existing Proxy Host (e.g., for your AllStarLink node domain)

2. Go to the **Custom Locations** tab

3. Click **Add Location** with these settings:
   - **Location:** `/skywarnplus-ng`
   - **Scheme:** `http`
   - **Forward Hostname/IP:** IP address of your ASL node (e.g., `127.0.0.1`)
   - **Forward Port:** `8100`

4. In the **Advanced** tab for this custom location, add:
   ```nginx
   rewrite ^/skywarnplus-ng/(.*)$ /$1 break;
   rewrite ^/skywarnplus-ng$ / break;

   proxy_set_header Upgrade $http_upgrade;
   proxy_set_header Connection "upgrade";
   proxy_buffering off;
   ```

   **Important Notes:**
   - The `rewrite` rules strip the `/skywarnplus-ng` prefix before forwarding to port 8100
   - Do **NOT** include `proxy_http_version 1.1;` as it can cause SSL errors in some NPM configurations
   - The WebSocket headers are essential for real-time weather alert updates

5. Save and access at `https://yourdomain.com/skywarnplus-ng`

## Verifying WebSocket Functionality

SkywarnPlus-NG uses WebSockets for real-time updates. To verify they're working:

1. Open the SkywarnPlus-NG interface in your browser
2. Open Developer Tools (F12)
3. Go to the **Network** tab
4. Filter by **WS** (WebSocket)
5. Refresh the page
6. You should see a WebSocket connection with status **101 Switching Protocols**

If you don't see any WebSocket connections or they show errors, double-check that:
- The WebSocket proxy headers are configured in the Advanced tab
- There are no firewall rules blocking WebSocket connections

## Troubleshooting

### 404 Not Found Error

**Cause:** NPM is forwarding the request with the subpath included (e.g., `/skywarnplus-ng/`) but SkywarnPlus-NG expects requests at the root (`/`).

**Solution:** Ensure the `rewrite` rules are correctly configured in the Advanced tab to strip the subpath prefix.

### ERR_SSL_UNRECOGNIZED_NAME_ALERT

**Cause:** This can occur if `proxy_http_version 1.1;` is included in custom location configurations.

**Solution:** Remove the `proxy_http_version 1.1;` directive from the Advanced configuration. NPM handles HTTP version negotiation automatically.

### WebSocket Connection Failures

**Cause:** Missing or incorrect WebSocket proxy headers.

**Solution:** Ensure these headers are in your configuration:
```nginx
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
```

### Connection Timeout

**Cause:** WebSocket connections timing out due to default proxy timeouts.

**Solution:** Add these timeout settings to your Advanced configuration:
```nginx
proxy_read_timeout 7d;
proxy_send_timeout 7d;
proxy_connect_timeout 7d;
```

## Security Considerations

- Always use HTTPS/SSL for external access to protect your credentials and data
- Consider using HTTP Basic Authentication in NPM for additional security
- Restrict access by IP address if SkywarnPlus-NG should only be accessible from specific networks
- Keep NPM and SkywarnPlus-NG updated to the latest versions

## Additional Resources

- [Nginx Proxy Manager Documentation](https://nginxproxymanager.com/)
- [SkywarnPlus-NG GitHub Repository](https://github.com/hardenedpenguin/SkywarnPlus-NG)
- [AllStarLink Documentation](https://allstarlink.org)

## Contributing

If you encounter issues or have improvements to this guide, please submit a pull request or open an issue on the SkywarnPlus-NG GitHub repository.

---

**Last Updated:** January 2026  
**Tested With:** Nginx Proxy Manager 2.x, SkywarnPlus-NG on ASL3
