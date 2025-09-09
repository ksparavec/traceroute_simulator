/**
 * TSIM WSGI API Configuration
 * Centralized API endpoint configuration for all pages
 */

const TSIM_API = {
    // Base URL for API endpoints
    BASE_URL: '',
    
    // API Endpoints
    ENDPOINTS: {
        LOGIN: '/login',
        LOGOUT: '/logout',
        MAIN: '/main',
        PDF: '/pdf',
        PROGRESS: '/progress',
        PROGRESS_STREAM: '/progress-stream',
        SERVICES_CONFIG: '/services-config',
        TEST_CONFIG: '/test-config',
        CLEANUP: '/cleanup'
    },
    
    /**
     * Make an API request with standard error handling
     */
    async request(endpoint, options = {}) {
        try {
            const response = await fetch(endpoint, {
                ...options,
                headers: {
                    ...options.headers,
                    'X-Requested-With': 'XMLHttpRequest'
                }
            });
            
            if (!response.ok) {
                if (response.status === 401) {
                    // Unauthorized - redirect to login
                    window.location.href = '/login.html';
                    return null;
                }
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            // Try to parse as JSON, fallback to text
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                return await response.json();
            } else {
                return await response.text();
            }
        } catch (error) {
            console.error('API request failed:', error);
            throw error;
        }
    },
    
    /**
     * Check if user is authenticated
     */
    async checkAuth() {
        try {
            const result = await this.request(this.ENDPOINTS.LOGIN);
            return result && result.success && result.logged_in;
        } catch (error) {
            return false;
        }
    },
    
    /**
     * Login user
     */
    async login(username, password) {
        const formData = new FormData();
        formData.append('username', username);
        formData.append('password', password);
        
        return await this.request(this.ENDPOINTS.LOGIN, {
            method: 'POST',
            body: formData
        });
    },
    
    /**
     * Logout user
     */
    async logout() {
        return await this.request(this.ENDPOINTS.LOGOUT, {
            method: 'POST'
        });
    },
    
    /**
     * Submit test request
     */
    async submitTest(formData) {
        return await this.request(this.ENDPOINTS.MAIN, {
            method: 'POST',
            body: formData
        });
    },
    
    /**
     * Get test progress
     */
    async getProgress(runId) {
        return await this.request(`${this.ENDPOINTS.PROGRESS}?run_id=${runId}`);
    },
    
    /**
     * Start progress stream (Server-Sent Events)
     */
    startProgressStream(runId, onMessage, onError) {
        const eventSource = new EventSource(`${this.ENDPOINTS.PROGRESS_STREAM}?run_id=${runId}`);
        
        eventSource.addEventListener('progress', (event) => {
            try {
                const data = JSON.parse(event.data);
                onMessage('progress', data);
            } catch (error) {
                console.error('Error parsing progress data:', error);
            }
        });
        
        eventSource.addEventListener('complete', (event) => {
            try {
                const data = JSON.parse(event.data);
                onMessage('complete', data);
                eventSource.close();
            } catch (error) {
                console.error('Error parsing complete data:', error);
            }
        });
        
        eventSource.addEventListener('error', (event) => {
            if (eventSource.readyState === EventSource.CLOSED) {
                onMessage('closed', null);
            } else {
                onError(event);
            }
        });
        
        return eventSource;
    },
    
    /**
     * Get PDF URL for a run
     */
    getPdfUrl(runId) {
        return `${this.ENDPOINTS.PDF}?run_id=${runId}`;
    },
    
    /**
     * Get services configuration
     */
    async getServicesConfig() {
        return await this.request(this.ENDPOINTS.SERVICES_CONFIG);
    },
    
    /**
     * Get test configuration
     */
    async getTestConfig() {
        return await this.request(this.ENDPOINTS.TEST_CONFIG);
    },
    
    /**
     * Perform cleanup (admin only)
     */
    async performCleanup(options = {}) {
        const formData = new FormData();
        for (const [key, value] of Object.entries(options)) {
            formData.append(key, value);
        }
        
        return await this.request(this.ENDPOINTS.CLEANUP, {
            method: 'POST',
            body: formData
        });
    }
};

// Make API object available globally
window.TSIM_API = TSIM_API;