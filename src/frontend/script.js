const { createApp } = Vue;

const i18n = {
    en: {
        newChat: 'New Chat', history: 'History', settings: 'Settings',
        clearChat: 'Clear Chat', logout: 'Logout',
        placeholder: 'Ask me about studying abroad... (Shift+Enter for new line)',
        thinking: 'Thinking...', login: 'Login', register: 'Register',
        loginTitle: 'Login to EduPilot', registerTitle: 'Register for EduPilot',
        authDesc: 'Log in to access study-abroad advisory and chat history.',
        username: 'Username', password: 'Password',
        roleUser: 'User', roleAdmin: 'Admin', adminCode: 'Admin invite code',
        submitting: 'Submitting...', goRegister: "Don't have an account? Register",
        goLogin: 'Already have an account? Login',
        settingsWip: 'Coming soon', noHistory: 'No history yet',
        messages: 'messages', deleteSession: 'Delete session',
        online: 'EduPilot Online', welcomeTitle: 'Hello! I\'m EduPilot',
        welcomeDesc: 'Your study-abroad advisor. I can search programs, check visas, and plan timelines.',
        send: 'Send', stop: 'Stop', disclaimer: 'AI-generated content may contain errors.',
        confirmClear: 'Clear current chat?', confirmDelete: 'Delete session',
        sessionExpired: 'Session expired, please log in again',
        authFailed: 'Authentication failed', emptyCredentials: 'Username and password required',
        tool_query_programs_calling: 'Searching programs...',
        tool_query_programs_done: 'Programs found',
        tool_check_visa_eligibility_calling: 'Checking visa requirements...',
        tool_check_visa_eligibility_done: 'Visa info retrieved',
        tool_calculate_timeline_calling: 'Calculating timeline...',
        tool_calculate_timeline_done: 'Timeline generated',
        tool_update_user_profile_calling: 'Updating profile...',
        tool_update_user_profile_done: 'Profile updated',
        tool_get_user_profile_calling: 'Loading profile...',
        tool_get_user_profile_done: 'Profile loaded',
        tool_save_note_calling: 'Saving note...',
        tool_save_note_done: 'Note saved',
        tool_default_calling: 'Processing...',
        tool_default_done: 'Done',
    },
    zh: {
        newChat: '新建会话', history: '历史记录', settings: '设置',
        clearChat: '清空当前对话', logout: '退出登录',
        placeholder: '问我留学相关的问题吧... (Shift+Enter 换行)',
        thinking: '正在思考中...', login: '登录', register: '注册',
        loginTitle: '登录 EduPilot', registerTitle: '注册 EduPilot',
        authDesc: '登录后即可使用留学咨询服务和历史记录。',
        username: '用户名', password: '密码',
        roleUser: '普通用户', roleAdmin: '管理员', adminCode: '管理员邀请码',
        submitting: '提交中...', goRegister: '没有账号？去注册',
        goLogin: '已有账号？去登录',
        settingsWip: '功能开发中', noHistory: '暂无历史记录',
        messages: '条消息', deleteSession: '删除会话',
        online: 'EduPilot 在线中...', welcomeTitle: '你好！我是 EduPilot',
        welcomeDesc: '你的留学咨询助手。可以帮你查学校、看签证、规划时间线。',
        send: '发送', stop: '终止', disclaimer: 'AI 生成的内容可能包含错误，请仔细甄别。',
        confirmClear: '确定要清空当前对话吗？', confirmDelete: '确定要删除会话',
        sessionExpired: '登录已过期，请重新登录',
        authFailed: '认证失败', emptyCredentials: '用户名和密码不能为空',
        tool_query_programs_calling: '正在查询学校数据库...',
        tool_query_programs_done: '找到匹配项目',
        tool_check_visa_eligibility_calling: '正在检查签证要求...',
        tool_check_visa_eligibility_done: '签证信息已获取',
        tool_calculate_timeline_calling: '正在计算时间线...',
        tool_calculate_timeline_done: '时间线已生成',
        tool_update_user_profile_calling: '正在更新用户档案...',
        tool_update_user_profile_done: '档案已更新',
        tool_get_user_profile_calling: '正在读取用户档案...',
        tool_get_user_profile_done: '档案已读取',
        tool_save_note_calling: '正在保存备注...',
        tool_save_note_done: '备注已保存',
        tool_default_calling: '处理中...',
        tool_default_done: '完成',
    }
};

createApp({
    data() {
        return {
            messages: [],
            userInput: '',
            isLoading: false,
            activeNav: 'newChat',
            abortController: null,
            sessionId: 'session_' + Date.now(),
            sessions: [],
            showHistorySidebar: false,
            isComposing: false,
            locale: localStorage.getItem('edupilot_locale') || 'en',
            token: localStorage.getItem('accessToken') || '',
            currentUser: null,
            authMode: 'login',
            authForm: { username: '', password: '', role: 'user', admin_code: '' },
            authLoading: false
        };
    },
    computed: {
        isAuthenticated() { return !!this.token && !!this.currentUser; },
        isAdmin() { return this.currentUser?.role === 'admin'; }
    },
    async mounted() {
        this.configureMarked();
        if (this.token) {
            try { await this.fetchMe(); } catch (_) { this.handleLogout(); }
        }
    },
    methods: {
        t(key) { return (i18n[this.locale] || i18n.en)[key] || (i18n.en[key] || key); },

        toolLabel(toolName, status) {
            const key = `tool_${toolName}_${status}`;
            const fallbackKey = `tool_default_${status}`;
            return this.t(key) !== key ? this.t(key) : this.t(fallbackKey);
        },

        toggleLocale() {
            this.locale = this.locale === 'en' ? 'zh' : 'en';
            localStorage.setItem('edupilot_locale', this.locale);
        },

        configureMarked() {
            marked.setOptions({
                highlight: (code, lang) => {
                    const language = hljs.getLanguage(lang) ? lang : 'plaintext';
                    return hljs.highlight(code, { language }).value;
                },
                langPrefix: 'hljs language-', breaks: true, gfm: true
            });
        },
        parseMarkdown(text) { return marked.parse(text); },
        escapeHtml(text) { const d = document.createElement('div'); d.textContent = text; return d.innerHTML; },

        authHeaders(extra = {}) {
            const h = { ...extra };
            if (this.token) h.Authorization = `Bearer ${this.token}`;
            return h;
        },
        async authFetch(url, options = {}) {
            const opts = { ...options };
            opts.headers = this.authHeaders(opts.headers || {});
            const r = await fetch(url, opts);
            if (r.status === 401) { this.handleLogout(); throw new Error(this.t('sessionExpired')); }
            return r;
        },
        async fetchMe() {
            const r = await this.authFetch('/auth/me');
            if (!r.ok) throw new Error(this.t('authFailed'));
            this.currentUser = await r.json();
        },

        async handleAuthSubmit() {
            if (this.authLoading) return;
            const username = this.authForm.username.trim();
            const password = this.authForm.password.trim();
            if (!username || !password) { alert(this.t('emptyCredentials')); return; }
            this.authLoading = true;
            try {
                const endpoint = this.authMode === 'login' ? '/auth/login' : '/auth/register';
                const payload = { username, password };
                if (this.authMode === 'register') {
                    payload.role = this.authForm.role;
                    payload.admin_code = this.authForm.admin_code || null;
                }
                const r = await fetch(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
                const data = await r.json().catch(() => ({}));
                if (!r.ok) throw new Error(data.detail || this.t('authFailed'));
                this.token = data.access_token;
                this.currentUser = { username: data.username, role: data.role };
                localStorage.setItem('accessToken', this.token);
                this.authForm.password = '';
                this.authForm.admin_code = '';
                this.messages = [];
                this.sessionId = 'session_' + Date.now();
                this.activeNav = 'newChat';
            } catch (e) { alert(e.message); }
            finally { this.authLoading = false; }
        },

        handleLogout() {
            this.token = ''; this.currentUser = null; this.messages = []; this.sessions = [];
            this.activeNav = 'newChat'; this.showHistorySidebar = false;
            localStorage.removeItem('accessToken');
        },

        handleCompositionStart() { this.isComposing = true; },
        handleCompositionEnd() { this.isComposing = false; },
        handleKeyDown(e) { if (e.key === 'Enter' && !e.shiftKey && !this.isComposing) { e.preventDefault(); this.handleSend(); } },
        handleStop() { if (this.abortController) this.abortController.abort(); },

        async handleSend() {
            if (!this.isAuthenticated) { alert(this.t('login')); return; }
            const text = this.userInput.trim();
            if (!text || this.isLoading || this.isComposing) return;

            this.messages.push({ text, isUser: true });
            this.userInput = '';
            this.$nextTick(() => { this.resetTextareaHeight(); this.scrollToBottom(); });

            this.isLoading = true;
            this.messages.push({ text: '', isUser: false, isThinking: true, toolSteps: [] });
            const botIdx = this.messages.length - 1;
            this.abortController = new AbortController();

            try {
                const r = await this.authFetch('/chat/stream', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: text, session_id: this.sessionId }),
                    signal: this.abortController.signal,
                });
                if (!r.ok) throw new Error(`HTTP ${r.status}`);
                const reader = r.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    let idx;
                    while ((idx = buffer.indexOf('\n\n')) !== -1) {
                        const eventStr = buffer.slice(0, idx);
                        buffer = buffer.slice(idx + 2);
                        if (!eventStr.startsWith('data: ')) continue;
                        const dataStr = eventStr.slice(6);
                        if (dataStr === '[DONE]') continue;
                        try {
                            const data = JSON.parse(dataStr);
                            if (data.type === 'content') {
                                this.messages[botIdx].isThinking = false;
                                this.messages[botIdx].text += data.content;
                            } else if (data.type === 'tool_call') {
                                if (!this.messages[botIdx].toolSteps) this.messages[botIdx].toolSteps = [];
                                if (data.status === 'calling') {
                                    this.messages[botIdx].toolSteps.push({
                                        name: data.name, status: 'calling',
                                        label: this.toolLabel(data.name, 'calling')
                                    });
                                } else if (data.status === 'done') {
                                    const steps = this.messages[botIdx].toolSteps;
                                    const last = steps.findLast(s => s.name === data.name && s.status === 'calling');
                                    if (last) {
                                        last.status = 'done';
                                        last.label = this.toolLabel(data.name, 'done');
                                    }
                                }
                            } else if (data.type === 'error') {
                                this.messages[botIdx].isThinking = false;
                                this.messages[botIdx].text += `\n[Error: ${data.content}]`;
                            }
                        } catch (e) { console.warn('SSE parse:', e); }
                    }
                    this.$nextTick(() => this.scrollToBottom());
                }
            } catch (error) {
                this.messages[botIdx].isThinking = false;
                if (error.name === 'AbortError') {
                    this.messages[botIdx].text += this.messages[botIdx].text ? '\n\n_(Stopped)_' : '(Stopped)';
                } else {
                    this.messages[botIdx].text = `Error: ${error.message}`;
                }
            } finally {
                this.isLoading = false; this.abortController = null;
                this.$nextTick(() => this.scrollToBottom());
            }
        },

        autoResize(e) { const t = e.target; t.style.height = 'auto'; t.style.height = t.scrollHeight + 'px'; },
        resetTextareaHeight() { if (this.$refs.textarea) this.$refs.textarea.style.height = 'auto'; },
        scrollToBottom() { if (this.$refs.chatContainer) this.$refs.chatContainer.scrollTop = this.$refs.chatContainer.scrollHeight; },

        handleNewChat() {
            if (!this.isAuthenticated) return;
            this.messages = []; this.sessionId = 'session_' + Date.now();
            this.activeNav = 'newChat'; this.showHistorySidebar = false;
        },
        handleClearChat() { if (confirm(this.t('confirmClear'))) this.messages = []; },

        async handleHistory() {
            if (!this.isAuthenticated) return;
            this.activeNav = 'history'; this.showHistorySidebar = true;
            try {
                const r = await this.authFetch('/chat/sessions');
                if (!r.ok) throw new Error('Failed');
                this.sessions = (await r.json()).sessions;
            } catch (e) { alert(e.message); }
        },

        async loadSession(sessionId) {
            this.sessionId = sessionId; this.showHistorySidebar = false; this.activeNav = 'newChat';
            try {
                const r = await this.authFetch(`/chat/sessions/${encodeURIComponent(sessionId)}`);
                if (!r.ok) throw new Error('Failed');
                const data = await r.json();
                this.messages = data.messages.map(m => ({ text: m.content, isUser: m.type === 'human' }));
                this.$nextTick(() => this.scrollToBottom());
            } catch (e) { alert(e.message); this.messages = []; }
        },

        async deleteSession(sessionId) {
            if (!confirm(`${this.t('confirmDelete')} "${sessionId}"?`)) return;
            try {
                const r = await this.authFetch(`/chat/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });
                if (!r.ok) { const d = await r.json().catch(() => ({})); throw new Error(d.detail || 'Failed'); }
                this.sessions = this.sessions.filter(s => s.session_id !== sessionId);
                if (this.sessionId === sessionId) { this.messages = []; this.sessionId = 'session_' + Date.now(); this.activeNav = 'newChat'; }
            } catch (e) { alert(e.message); }
        },

        handleSettings() { this.activeNav = 'settings'; this.showHistorySidebar = false; }
    },
    watch: { messages: { handler() { this.$nextTick(() => this.scrollToBottom()); }, deep: true } }
}).mount('#app');
