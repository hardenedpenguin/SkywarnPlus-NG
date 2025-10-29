/**
 * Official JavaScript SDK for SkywarnPlus-NG API
 */

const axios = require('axios');

class SkywarnPlusError extends Error {
    constructor(message, status, response) {
        super(message);
        this.name = 'SkywarnPlusError';
        this.status = status;
        this.response = response;
    }
}

class SkywarnPlusClient {
    /**
     * Initialize the SkywarnPlus-NG client
     * @param {string} baseUrl - Base URL of the SkywarnPlus-NG API
     * @param {number} timeout - Request timeout in milliseconds
     */
    constructor(baseUrl = '{{ base_url }}', timeout = 30000) {
        this.baseUrl = baseUrl.replace(/\/$/, '');
        this.timeout = timeout;
        
        this.client = axios.create({
            baseURL: this.baseUrl,
            timeout: this.timeout,
            headers: {
                'Content-Type': 'application/json',
                'User-Agent': 'SkywarnPlus-JS-SDK/{{ version }}'
            }
        });
        
        // Add response interceptor for error handling
        this.client.interceptors.response.use(
            response => response,
            error => {
                if (error.response) {
                    const message = error.response.data?.error || error.message;
                    throw new SkywarnPlusError(message, error.response.status, error.response.data);
                } else if (error.request) {
                    throw new SkywarnPlusError('Network error: No response received', 0, null);
                } else {
                    throw new SkywarnPlusError(`Request error: ${error.message}`, 0, null);
                }
            }
        );
    }
    
    /**
     * Make HTTP request to API
     * @private
     */
    async _makeRequest(method, endpoint, data = null, params = {}) {
        try {
            const response = await this.client.request({
                method,
                url: endpoint,
                data,
                params
            });
            return response.data;
        } catch (error) {
            throw error;
        }
    }
    
    /**
     * Get system status
     * @returns {Promise<Object>} System status information
     */
    async getStatus() {
        return this._makeRequest('GET', '/api/status');
    }
    
    /**
     * Get system health information
     * @returns {Promise<Object>} System health information
     */
    async getHealth() {
        return this._makeRequest('GET', '/api/health');
    }
    
    /**
     * Get active weather alerts
     * @param {string} county - Filter by county code
     * @param {string} severity - Filter by severity level
     * @returns {Promise<Array>} Array of weather alerts
     */
    async getAlerts(county = null, severity = null) {
        const params = {};
        if (county) params.county = county;
        if (severity) params.severity = severity;
        
        return this._makeRequest('GET', '/api/alerts', null, params);
    }
    
    /**
     * Get alert history
     * @param {number} limit - Maximum number of alerts to return
     * @param {number} offset - Number of alerts to skip
     * @param {string} startDate - Start date filter (ISO 8601)
     * @param {string} endDate - End date filter (ISO 8601)
     * @returns {Promise<Object>} Alert history with pagination
     */
    async getAlertHistory(limit = 100, offset = 0, startDate = null, endDate = null) {
        const params = { limit, offset };
        if (startDate) params.start_date = startDate;
        if (endDate) params.end_date = endDate;
        
        return this._makeRequest('GET', '/api/alerts/history', null, params);
    }
    
    /**
     * Get system configuration
     * @returns {Promise<Object>} System configuration
     */
    async getConfiguration() {
        return this._makeRequest('GET', '/api/config');
    }
    
    /**
     * Update system configuration
     * @param {Object} config - Configuration object
     * @returns {Promise<Object>} Update result
     */
    async updateConfiguration(config) {
        return this._makeRequest('POST', '/api/config', config);
    }
    
    /**
     * Reset configuration to defaults
     * @returns {Promise<Object>} Reset result
     */
    async resetConfiguration() {
        return this._makeRequest('POST', '/api/config/reset');
    }
    
    /**
     * Test email SMTP connection
     * @param {Object} emailConfig - Email configuration
     * @returns {Promise<Object>} Test result
     */
    async testEmailConnection(emailConfig) {
        return this._makeRequest('POST', '/api/notifications/test-email', emailConfig);
    }
    
    /**
     * Get all notification subscribers
     * @returns {Promise<Array>} Array of subscribers
     */
    async getSubscribers() {
        return this._makeRequest('GET', '/api/notifications/subscribers');
    }
    
    /**
     * Add a new notification subscriber
     * @param {Object} subscriberData - Subscriber data
     * @returns {Promise<Object>} Add result
     */
    async addSubscriber(subscriberData) {
        return this._makeRequest('POST', '/api/notifications/subscribers', subscriberData);
    }
    
    /**
     * Update an existing subscriber
     * @param {string} subscriberId - Subscriber ID
     * @param {Object} subscriberData - Updated subscriber data
     * @returns {Promise<Object>} Update result
     */
    async updateSubscriber(subscriberId, subscriberData) {
        return this._makeRequest('PUT', `/api/notifications/subscribers/${subscriberId}`, subscriberData);
    }
    
    /**
     * Delete a subscriber
     * @param {string} subscriberId - Subscriber ID
     * @returns {Promise<Object>} Delete result
     */
    async deleteSubscriber(subscriberId) {
        return this._makeRequest('DELETE', `/api/notifications/subscribers/${subscriberId}`);
    }
    
    /**
     * Get all notification templates
     * @returns {Promise<Object>} Templates by type
     */
    async getTemplates() {
        return this._makeRequest('GET', '/api/notifications/templates');
    }
    
    /**
     * Add a new notification template
     * @param {Object} templateData - Template data
     * @returns {Promise<Object>} Add result
     */
    async addTemplate(templateData) {
        return this._makeRequest('POST', '/api/notifications/templates', templateData);
    }
    
    /**
     * Get system logs
     * @param {string} level - Log level filter
     * @param {number} limit - Maximum number of log entries
     * @param {string} since - Get logs since timestamp
     * @returns {Promise<Array>} Array of log entries
     */
    async getLogs(level = null, limit = 100, since = null) {
        const params = { limit };
        if (level) params.level = level;
        if (since) params.since = since;
        
        return this._makeRequest('GET', '/api/logs', null, params);
    }
    
    /**
     * Get system metrics
     * @returns {Promise<Object>} System metrics
     */
    async getMetrics() {
        return this._makeRequest('GET', '/api/metrics');
    }
    
    /**
     * Get database statistics
     * @returns {Promise<Object>} Database statistics
     */
    async getDatabaseStats() {
        return this._makeRequest('GET', '/api/database/stats');
    }
    
    /**
     * Connect to WebSocket for real-time updates
     * @param {Function} onMessage - Message handler function
     * @param {Function} onError - Error handler function
     * @param {Function} onClose - Close handler function
     * @returns {WebSocket} WebSocket connection
     */
    connectWebSocket(onMessage, onError = null, onClose = null) {
        const wsUrl = this.baseUrl.replace(/^http/, 'ws') + '/ws';
        const ws = new WebSocket(wsUrl);
        
        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                onMessage(data);
            } catch (error) {
                if (onError) {
                    onError(`Failed to parse message: ${error.message}`);
                }
            }
        };
        
        ws.onerror = (error) => {
            if (onError) {
                onError(`WebSocket error: ${error}`);
            }
        };
        
        ws.onclose = (event) => {
            if (onClose) {
                onClose(event);
            }
        };
        
        return ws;
    }
}

// Convenience functions
function createClient(baseUrl = '{{ base_url }}') {
    return new SkywarnPlusClient(baseUrl);
}

async function quickStatus(baseUrl = '{{ base_url }}') {
    const client = createClient(baseUrl);
    return client.getStatus();
}

async function quickAlerts(baseUrl = '{{ base_url }}', county = null) {
    const client = createClient(baseUrl);
    return client.getAlerts(county);
}

// Export for Node.js and browser
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        SkywarnPlusClient,
        SkywarnPlusError,
        createClient,
        quickStatus,
        quickAlerts
    };
} else {
    window.SkywarnPlus = {
        SkywarnPlusClient,
        SkywarnPlusError,
        createClient,
        quickStatus,
        quickAlerts
    };
}
