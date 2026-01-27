import React, { useState, useEffect } from 'react';
import { X, Palette, Check, Settings as SettingsIcon, Bell, Shield, Database, Server, Plus, Trash2, Edit2, Save } from 'lucide-react';
import DataExportImport from './DataExportImport';
import { THEMES, applyTheme, getStoredTheme } from '../themes';
import { toast } from 'sonner';

const SettingsModal = ({ isOpen, onClose, tabs, setTabs, favorites, setFavorites }) => {
  const [selectedTheme, setSelectedTheme] = useState(getStoredTheme());
  const [activeTab, setActiveTab] = useState('appearance');

  useEffect(() => {
    setSelectedTheme(getStoredTheme());
  }, [isOpen]);

  if (!isOpen) return null;

  const handleThemeChange = (themeId) => {
    setSelectedTheme(themeId);
    applyTheme(themeId);
  };

  const darkThemes = Object.values(THEMES).filter(t => t.type === 'dark');
  const lightThemes = Object.values(THEMES).filter(t => t.type === 'light');

  const settingsTabs = [
    { id: 'appearance', name: 'Appearance', icon: Palette },
    { id: 'environment', name: 'Environment', icon: Server },
    { id: 'data', name: 'Data & Backup', icon: Database },
    { id: 'general', name: 'General', icon: SettingsIcon },
    { id: 'notifications', name: 'Notifications', icon: Bell },
    { id: 'security', name: 'Security', icon: Shield },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-[var(--bg-secondary)] border border-[var(--border-primary)] rounded-lg shadow-2xl w-full max-w-4xl mx-4 max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-[var(--border-primary)]">
          <div>
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">Settings</h2>
            <p className="text-sm text-[var(--text-tertiary)]">Customize your Devvy Studio experience</p>
          </div>
          <button
            onClick={onClose}
            className="text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors"
            aria-label="Close settings"
          >
            <X className="w-5 h-5" aria-hidden="true" />
          </button>
        </div>

        {/* Tabs and Content */}
        <div className="flex flex-1 overflow-hidden">
          {/* Sidebar Tabs */}
          <div className="w-48 border-r border-[var(--border-primary)] p-4 space-y-1">
            {settingsTabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`
                    w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-colors
                    ${activeTab === tab.id
                      ? 'bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]'
                      : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)] hover:text-[var(--text-primary)]'
                    }
                  `}
                >
                  <Icon className="w-4 h-4" />
                  {tab.name}
                </button>
              );
            })}
          </div>

          {/* Content Area */}
          <div className="flex-1 overflow-y-auto p-6">
            {activeTab === 'appearance' && (
              <div className="space-y-6">
                <div>
                  <h3 className="text-base font-semibold text-[var(--text-primary)] mb-1">Theme</h3>
                  <p className="text-sm text-[var(--text-tertiary)]">Choose your preferred color theme</p>
                </div>

                {/* Dark Themes */}
                <div className="space-y-3">
                  <h4 className="text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wide">Dark Themes</h4>
                  <div className="grid grid-cols-1 gap-2">
                    {darkThemes.map((theme) => (
                      <ThemeOption
                        key={theme.id}
                        theme={theme}
                        isSelected={selectedTheme === theme.id}
                        onSelect={() => handleThemeChange(theme.id)}
                      />
                    ))}
                  </div>
                </div>

                {/* Light Themes */}
                <div className="space-y-3">
                  <h4 className="text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wide">Light Themes</h4>
                  <div className="grid grid-cols-1 gap-2">
                    {lightThemes.map((theme) => (
                      <ThemeOption
                        key={theme.id}
                        theme={theme}
                        isSelected={selectedTheme === theme.id}
                        onSelect={() => handleThemeChange(theme.id)}
                      />
                    ))}
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'environment' && (
              <EnvironmentSettings />
            )}

            {activeTab === 'general' && (
              <div className="space-y-6">
                <div>
                  <h3 className="text-base font-semibold text-[var(--text-primary)] mb-1">General Settings</h3>
                  <p className="text-sm text-[var(--text-tertiary)]">Configure general application settings</p>
                </div>
                <div className="text-sm text-[var(--text-tertiary)] p-8 text-center">
                  Coming soon...
                </div>
              </div>
            )}

            {activeTab === 'notifications' && (
              <div className="space-y-6">
                <div>
                  <h3 className="text-base font-semibold text-[var(--text-primary)] mb-1">Notifications</h3>
                  <p className="text-sm text-[var(--text-tertiary)]">Manage notification preferences</p>
                </div>
                <div className="text-sm text-[var(--text-tertiary)] p-8 text-center">
                  Coming soon...
                </div>
              </div>
            )}

            {activeTab === 'security' && (
              <div className="space-y-6">
                <div>
                  <h3 className="text-base font-semibold text-[var(--text-primary)] mb-1">Security & Privacy</h3>
                  <p className="text-sm text-[var(--text-tertiary)]">Manage security and privacy settings</p>
                </div>
                <div className="text-sm text-[var(--text-tertiary)] p-8 text-center">
                  Coming soon...
                </div>
              </div>
            )}
            
            {activeTab === 'data' && (
              <DataExportImport 
                tabs={tabs} 
                setTabs={setTabs} 
                favorites={favorites} 
                setFavorites={setFavorites} 
              />
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-4 border-t border-[var(--border-primary)]">
          <p className="text-xs text-[var(--text-tertiary)]">
            Settings are saved automatically
          </p>
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium bg-[var(--accent-primary)] hover:bg-[var(--accent-secondary)] text-white rounded-lg transition-colors"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
};

const ThemeOption = ({ theme, isSelected, onSelect }) => {
  return (
    <button
      onClick={onSelect}
      className={`
        relative flex items-center gap-3 p-3 rounded-lg border-2 transition-all
        ${isSelected 
          ? 'border-[var(--accent-primary)] bg-[var(--accent-primary)]/5' 
          : 'border-[var(--border-primary)] hover:border-[var(--border-focus)] bg-[var(--bg-tertiary)]'
        }
      `}
    >
      {/* Color Preview */}
      <div className="flex gap-1">
        <div 
          className="w-6 h-6 rounded border border-[var(--border-primary)]" 
          style={{ backgroundColor: theme.colors['--bg-primary'] }}
        />
        <div 
          className="w-6 h-6 rounded border border-[var(--border-primary)]" 
          style={{ backgroundColor: theme.colors['--bg-tertiary'] }}
        />
        <div 
          className="w-6 h-6 rounded border border-[var(--border-primary)]" 
          style={{ backgroundColor: theme.colors['--accent-primary'] }}
        />
      </div>

      {/* Theme Info */}
      <div className="flex-1 text-left">
        <div className="text-sm font-medium text-[var(--text-primary)]">{theme.name}</div>
      </div>

      {/* Selected Indicator */}
      {isSelected && (
        <div className="w-5 h-5 rounded-full bg-[var(--accent-primary)] flex items-center justify-center flex-shrink-0">
          <Check className="w-3 h-3 text-white" />
        </div>
      )}
    </button>
  );
};

const EnvironmentSettings = () => {
  const [activeCategory, setActiveCategory] = useState('llm');
  const [configs, setConfigs] = useState({});
  const [editingConfig, setEditingConfig] = useState(null);

  const categories = [
    { id: 'llm', name: 'LLM / AI', key: 'llm_config' },
    { id: 'git', name: 'Git Repositories', key: 'git_repositories' },
    { id: 'kafka', name: 'Kafka', key: 'kafka_configs' },
    { id: 'filebeat', name: 'Filebeat', key: 'filebeat_configs' },
    { id: 'vector', name: 'Vector', key: 'vector_configs' },
    { id: 'datasource', name: 'Data Sources', key: 'datasource_configs' },
    { id: 'execution', name: 'Code Execution', key: 'execution_configs' },
  ];

  useEffect(() => {
    loadAllConfigs();
  }, []);

  const loadAllConfigs = () => {
    const allConfigs = {};
    categories.forEach(cat => {
      try {
        const stored = localStorage.getItem(cat.key);
        allConfigs[cat.key] = stored ? JSON.parse(stored) : (cat.id === 'llm' ? {} : []);
      } catch (e) {
        allConfigs[cat.key] = cat.id === 'llm' ? {} : [];
      }
    });
    setConfigs(allConfigs);
  };

  const saveConfig = (key, value) => {
    localStorage.setItem(key, JSON.stringify(value));
    setConfigs(prev => ({ ...prev, [key]: value }));
    toast.success('Configuration saved');
  };

  const activeKey = categories.find(c => c.id === activeCategory)?.key;
  const activeConfig = configs[activeKey];

  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-base font-semibold text-[var(--text-primary)] mb-1">Environment Configuration</h3>
        <p className="text-sm text-[var(--text-tertiary)]">Configure external services and integrations</p>
      </div>

      <div className="flex gap-4">
        {/* Category Sidebar */}
        <div className="w-48 space-y-1">
          {categories.map(cat => (
            <button
              key={cat.id}
              onClick={() => setActiveCategory(cat.id)}
              className={`w-full text-left px-3 py-2 rounded-md text-sm transition-colors ${
                activeCategory === cat.id
                  ? 'bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] font-medium'
                  : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]'
              }`}
            >
              {cat.name}
            </button>
          ))}
        </div>

        {/* Config Content */}
        <div className="flex-1">
          {activeCategory === 'llm' && (
            <LLMConfig config={activeConfig} onSave={(val) => saveConfig(activeKey, val)} />
          )}
          {activeCategory !== 'llm' && (
            <ArrayConfig 
              config={activeConfig || []} 
              category={activeCategory}
              onSave={(val) => saveConfig(activeKey, val)} 
            />
          )}
        </div>
      </div>
    </div>
  );
};

const LLMConfig = ({ config, onSave }) => {
  const [formData, setFormData] = useState(config || {
    provider: 'openai',
    apiKey: '',
    model: 'gpt-4',
    apiUrl: 'https://api.openai.com/v1',
    temperature: 0.7,
    maxTokens: 2000,
    customHeaders: {},
    requestFormat: 'openai'
  });

  useEffect(() => {
    setFormData(config || {
      provider: 'openai',
      apiKey: '',
      model: 'gpt-4',
      apiUrl: 'https://api.openai.com/v1',
      temperature: 0.7,
      maxTokens: 2000,
      customHeaders: {},
      requestFormat: 'openai'
    });
  }, [config]);

  const handleSave = () => {
    onSave(formData);
  };

  const providerPresets = {
    openai: {
      apiUrl: 'https://api.openai.com/v1',
      model: 'gpt-4',
      requestFormat: 'openai'
    },
    anthropic: {
      apiUrl: 'https://api.anthropic.com/v1',
      model: 'claude-3-opus-20240229',
      requestFormat: 'anthropic'
    },
    ollama: {
      apiUrl: 'http://localhost:11434/api',
      model: 'llama2',
      requestFormat: 'ollama'
    },
    azure: {
      apiUrl: 'https://YOUR_RESOURCE.openai.azure.com',
      model: 'gpt-4',
      requestFormat: 'azure'
    },
    custom: {
      apiUrl: '',
      model: '',
      requestFormat: 'openai'
    }
  };

  const handleProviderChange = (provider) => {
    const preset = providerPresets[provider];
    setFormData({
      ...formData,
      provider,
      apiUrl: preset.apiUrl,
      model: preset.model,
      requestFormat: preset.requestFormat
    });
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-[var(--text-primary)] mb-1">Provider</label>
          <select
            value={formData.provider}
            onChange={(e) => handleProviderChange(e.target.value)}
            className="w-full px-3 py-2 border rounded-md bg-[var(--bg-tertiary)] border-[var(--border-primary)] text-[var(--text-primary)]"
          >
            <option value="openai">OpenAI</option>
            <option value="anthropic">Anthropic (Claude)</option>
            <option value="ollama">Ollama (Local)</option>
            <option value="azure">Azure OpenAI</option>
            <option value="custom">Custom (Self-hosted LLM/SLM)</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-[var(--text-primary)] mb-1">Model</label>
          <input
            type="text"
            value={formData.model}
            onChange={(e) => setFormData({...formData, model: e.target.value})}
            placeholder="gpt-4"
            className="w-full px-3 py-2 border rounded-md bg-[var(--bg-tertiary)] border-[var(--border-primary)] text-[var(--text-primary)]"
          />
        </div>
      </div>
      <div>
        <label className="block text-sm font-medium text-[var(--text-primary)] mb-1">API Key</label>
        <input
          type="password"
          value={formData.apiKey}
          onChange={(e) => setFormData({...formData, apiKey: e.target.value})}
          placeholder="sk-..."
          className="w-full px-3 py-2 border rounded-md bg-[var(--bg-tertiary)] border-[var(--border-primary)] text-[var(--text-primary)]"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-[var(--text-primary)] mb-1">API URL</label>
        <input
          type="text"
          value={formData.apiUrl}
          onChange={(e) => setFormData({...formData, apiUrl: e.target.value})}
          placeholder="https://api.openai.com/v1"
          className="w-full px-3 py-2 border rounded-md bg-[var(--bg-tertiary)] border-[var(--border-primary)] text-[var(--text-primary)]"
        />
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-[var(--text-primary)] mb-1">Temperature</label>
          <input
            type="number"
            step="0.1"
            min="0"
            max="2"
            value={formData.temperature}
            onChange={(e) => setFormData({...formData, temperature: parseFloat(e.target.value)})}
            className="w-full px-3 py-2 border rounded-md bg-[var(--bg-tertiary)] border-[var(--border-primary)] text-[var(--text-primary)]"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-[var(--text-primary)] mb-1">Max Tokens</label>
          <input
            type="number"
            value={formData.maxTokens}
            onChange={(e) => setFormData({...formData, maxTokens: parseInt(e.target.value)})}
            className="w-full px-3 py-2 border rounded-md bg-[var(--bg-tertiary)] border-[var(--border-primary)] text-[var(--text-primary)]"
          />
        </div>
      </div>

      {formData.provider === 'custom' && (
        <div className="space-y-4 p-4 border border-[var(--border-primary)] rounded-md bg-[var(--bg-secondary)]">
          <h4 className="text-sm font-semibold text-[var(--text-primary)]">Custom Configuration</h4>
          
          <div>
            <label className="block text-sm font-medium text-[var(--text-primary)] mb-1">Request Format</label>
            <select
              value={formData.requestFormat}
              onChange={(e) => setFormData({...formData, requestFormat: e.target.value})}
              className="w-full px-3 py-2 border rounded-md bg-[var(--bg-tertiary)] border-[var(--border-primary)] text-[var(--text-primary)]"
            >
              <option value="openai">OpenAI Compatible</option>
              <option value="anthropic">Anthropic Compatible</option>
              <option value="ollama">Ollama Compatible</option>
              <option value="huggingface">HuggingFace</option>
              <option value="custom-json">Custom JSON</option>
            </select>
            <p className="text-xs text-[var(--text-secondary)] mt-1">
              Select the API format your LLM/SLM uses
            </p>
          </div>

          <div>
            <label className="block text-sm font-medium text-[var(--text-primary)] mb-1">Custom Headers (JSON)</label>
            <textarea
              value={typeof formData.customHeaders === 'string' ? formData.customHeaders : JSON.stringify(formData.customHeaders, null, 2)}
              onChange={(e) => {
                try {
                  const parsed = JSON.parse(e.target.value);
                  setFormData({...formData, customHeaders: parsed});
                } catch {
                  setFormData({...formData, customHeaders: e.target.value});
                }
              }}
              placeholder={'{\n  "Authorization": "Bearer token",\n  "X-Custom-Header": "value"\n}'}
              rows={4}
              className="w-full px-3 py-2 border rounded-md bg-[var(--bg-tertiary)] border-[var(--border-primary)] text-[var(--text-primary)] font-mono text-xs"
            />
            <p className="text-xs text-[var(--text-secondary)] mt-1">
              Add custom HTTP headers for your API (optional)
            </p>
          </div>

          <div className="bg-blue-500/10 border border-blue-500/20 rounded-md p-3">
            <p className="text-xs text-blue-400 font-medium mb-1">💡 Examples of Self-hosted LLMs/SLMs:</p>
            <ul className="text-xs text-[var(--text-secondary)] space-y-1 ml-4">
              <li>• Ollama (llama2, mistral, codellama)</li>
              <li>• LM Studio (local models)</li>
              <li>• vLLM (high-performance inference)</li>
              <li>• Text Generation WebUI</li>
              <li>• LocalAI (OpenAI compatible)</li>
              <li>• HuggingFace Inference API</li>
              <li>• Custom FastAPI/Flask endpoints</li>
            </ul>
          </div>
        </div>
      )}

      <button
        onClick={handleSave}
        className="px-4 py-2 bg-[var(--accent-primary)] text-white rounded-md hover:bg-[var(--accent-secondary)] transition-colors"
      >
        <Save className="w-4 h-4 inline-block mr-2" />
        Save Configuration
      </button>
    </div>
  );
};

const ArrayConfig = ({ config, category, onSave }) => {
  const [items, setItems] = useState(config || []);
  const [editIndex, setEditIndex] = useState(null);
  const [editData, setEditData] = useState({});

  useEffect(() => {
    setItems(config || []);
  }, [config]);

  const addNew = () => {
    const newItem = { id: Date.now().toString(), name: '', ...getDefaultFields(category) };
    setEditIndex(items.length);
    setEditData(newItem);
    setItems([...items, newItem]);
  };

  const saveItem = () => {
    const updated = [...items];
    updated[editIndex] = editData;
    setItems(updated);
    onSave(updated);
    setEditIndex(null);
    setEditData({});
  };

  const deleteItem = (index) => {
    const updated = items.filter((_, i) => i !== index);
    setItems(updated);
    onSave(updated);
  };

  const getDefaultFields = (cat) => {
    switch(cat) {
      case 'git': return { owner: '', apiUrl: 'https://api.github.com', token: '' };
      case 'kafka': return { apiUrl: '', token: '' };
      case 'filebeat': return { apiUrl: '', token: '' };
      case 'vector': return { apiUrl: '', token: '' };
      case 'datasource': return { type: 'mysql', apiUrl: '', token: '', host: '', port: 3306, username: '', password: '' };
      case 'execution': return { apiUrl: '', wsUrl: '', token: '' };
      default: return {};
    }
  };

  return (
    <div className="space-y-4">
      <button
        onClick={addNew}
        className="px-4 py-2 bg-[var(--accent-primary)] text-white rounded-md hover:bg-[var(--accent-secondary)] transition-colors text-sm"
      >
        <Plus className="w-4 h-4 inline-block mr-2" />
        Add New
      </button>

      <div className="space-y-2">
        {items.map((item, index) => (
          <div key={item.id || index} className="border border-[var(--border-primary)] rounded-md p-4 bg-[var(--bg-tertiary)]">
            {editIndex === index ? (
              <div className="space-y-3">
                <input
                  type="text"
                  value={editData.name || ''}
                  onChange={(e) => setEditData({...editData, name: e.target.value})}
                  placeholder="Name"
                  className="w-full px-3 py-2 border rounded-md bg-[var(--bg-secondary)] border-[var(--border-primary)] text-[var(--text-primary)]"
                />
                {Object.keys(getDefaultFields(category)).map(field => (
                  <input
                    key={field}
                    type={field.includes('password') || field.includes('token') ? 'password' : 'text'}
                    value={editData[field] || ''}
                    onChange={(e) => setEditData({...editData, [field]: e.target.value})}
                    placeholder={field}
                    className="w-full px-3 py-2 border rounded-md bg-[var(--bg-secondary)] border-[var(--border-primary)] text-[var(--text-primary)]"
                  />
                ))}
                <div className="flex gap-2">
                  <button onClick={saveItem} className="px-3 py-1 bg-green-500 text-white rounded text-sm">Save</button>
                  <button onClick={() => setEditIndex(null)} className="px-3 py-1 bg-gray-500 text-white rounded text-sm">Cancel</button>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium text-[var(--text-primary)]">{item.name}</div>
                  <div className="text-xs text-[var(--text-secondary)]">{item.apiUrl || item.host}</div>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => { setEditIndex(index); setEditData(item); }}
                    className="p-1 hover:bg-[var(--bg-secondary)] rounded"
                    aria-label={`Edit ${item.name || 'item'}`}
                  >
                    <Edit2 className="w-4 h-4" aria-hidden="true" />
                  </button>
                  <button
                    onClick={() => deleteItem(index)}
                    className="p-1 hover:bg-red-500/10 text-red-500 rounded"
                    aria-label={`Delete ${item.name || 'item'}`}
                  >
                    <Trash2 className="w-4 h-4" aria-hidden="true" />
                  </button>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
};

export default SettingsModal;
