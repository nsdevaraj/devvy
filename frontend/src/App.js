import { useState, useEffect, useRef } from 'react';
import '@/App.css';
import axios from 'axios';
import Editor from '@monaco-editor/react';
import { 
  Menu, X, ChevronRight, Search, Star, Code, FileJson, 
  Globe, FileSpreadsheet, Copy, Check, AlertCircle, Settings, User,
  LogOut, Shield, Crown, Lock, Save, Bookmark
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import { Toaster } from '@/components/ui/sonner';
import { AuthProvider, useAuth } from '@/AuthContextDesktop';
import CollectionsPanel from '@/components/CollectionsPanel';
import SaveToCollectionDialog from '@/components/SaveToCollectionDialog';
import RestApiTester from '@/components/RestApiTester';
import GrpcTester from '@/components/GrpcTester';
import UiRecorder from '@/components/UiRecorder';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const CATEGORIES = [
  { id: 'json', name: 'JSON', icon: FileJson },
  { id: 'api', name: 'API', icon: Globe },
  { id: 'automation', name: 'Automation', icon: Globe },
  { id: 'xml', name: 'XML', icon: Code },
  { id: 'excel', name: 'Excel', icon: FileSpreadsheet },
];

const TOOLS = [
  { 
    id: 'json-beautifier', 
    name: 'JSON Beautifier', 
    category: 'json',
    icon: FileJson,
    description: 'Format and beautify JSON data'
  },
  { 
    id: 'json-validator', 
    name: 'JSON Validator', 
    category: 'json',
    icon: FileJson,
    description: 'Validate JSON structure'
  },
  { 
    id: 'api-tester', 
    name: 'REST API Tester', 
    category: 'api',
    icon: Globe,
    description: 'Test REST API endpoints'
  },
  { 
    id: 'grpc-tester', 
    name: 'gRPC Tester', 
    category: 'api',
    icon: Globe,
    description: 'Test gRPC services'
  },
  { 
    id: 'ui-recorder', 
    name: 'UI Automation Recorder', 
    category: 'automation',
    icon: Globe,
    description: 'Record browser interactions and generate Playwright code'
  },
];

function MainApp() {
  // Desktop version - no authentication needed
  const user = { name: 'Desktop User' };
  const isAdmin = false;
  const isPremium = false;
  const [activePane, setActivePane] = useState('categories');
  const [selectedCategory, setSelectedCategory] = useState(null);
  const [tabs, setTabs] = useState([]);
  const [activeTab, setActiveTab] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [favorites, setFavorites] = useState([]);
  const [showAdminPanel, setShowAdminPanel] = useState(false);
  const [showUpgrade, setShowUpgrade] = useState(false);
  const [toolsConfig, setToolsConfig] = useState({});
  const [showSaveDialog, setShowSaveDialog] = useState(false);
  const [tabToSave, setTabToSave] = useState(null);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  useEffect(() => {
    loadFavorites();
    loadToolsConfig();
  }, []);

  const loadFavorites = async () => {
    try {
      const response = await axios.get(`${API}/favorites/list`);
      setFavorites(response.data.favorites || []);
    } catch (error) {
      console.error('Failed to load favorites:', error);
    }
  };

  const loadToolsConfig = async () => {
    try {
      const response = await axios.get(`${API}/tools/config`, {
        headers: token ? {
          'Authorization': `Bearer ${token}`
        } : {}
      });
      const configMap = {};
      response.data.tools.forEach(tool => {
        configMap[tool.tool_id] = tool;
      });
      setToolsConfig(configMap);
    } catch (error) {
      console.error('Failed to load tools config:', error);
    }
  };

  const checkToolAccess = (toolId) => {
    const config = toolsConfig[toolId];
    if (!config || !config.is_premium) {
      return { hasAccess: true, isPremium: false };
    }
    return { hasAccess: isPremium, isPremium: true };
  };

  const toggleFavorite = async (toolId) => {
    try {
      if (favorites.includes(toolId)) {
        await axios.post(`${API}/favorites/remove`, { tool_id: toolId });
        setFavorites(favorites.filter(id => id !== toolId));
        toast.success('Removed from favorites');
      } else {
        await axios.post(`${API}/favorites/add`, { tool_id: toolId });
        setFavorites([...favorites, toolId]);
        toast.success('Added to favorites');
      }
    } catch (error) {
      console.error('Failed to toggle favorite:', error);
      toast.error('Failed to update favorites');
    }
  };

  const openTool = (tool) => {
    // Check if user has access to this tool
    const access = checkToolAccess(tool.id);
    
    if (access.isPremium && !access.hasAccess) {
      toast.error('This is a Premium feature. Please upgrade to access.');
      setShowUpgrade(true);
      return;
    }

    // Allow multiple instances of the same tool
    const newTab = {
      tabId: `${tool.id}-${Date.now()}`,
      ...tool,
      customName: null,
      data: {}
    };
    setTabs([...tabs, newTab]);
    setActiveTab(newTab.tabId);
  };

  const handleCategorySelect = (category) => {
    setSelectedCategory(category);
  };

  const handleBackToCategories = () => {
    setSelectedCategory(null);
  };

  const toggleSidebar = () => {
    setIsSidebarCollapsed(!isSidebarCollapsed);
  };

  const closeTab = (tabId, e) => {
    e?.stopPropagation();
    const tabIndex = tabs.findIndex(t => t.tabId === tabId);
    const newTabs = tabs.filter(t => t.tabId !== tabId);
    setTabs(newTabs);
    
    if (activeTab === tabId && newTabs.length > 0) {
      const newActiveIndex = Math.min(tabIndex, newTabs.length - 1);
      setActiveTab(newTabs[newActiveIndex].tabId);
    } else if (newTabs.length === 0) {
      setActiveTab(null);
    }
  };

  const closeOtherTabs = (tabId) => {
    const keepTab = tabs.find(t => t.tabId === tabId);
    setTabs([keepTab]);
    setActiveTab(tabId);
  };

  const closeTabsToRight = (tabId) => {
    const tabIndex = tabs.findIndex(t => t.tabId === tabId);
    const newTabs = tabs.slice(0, tabIndex + 1);
    setTabs(newTabs);
    if (!newTabs.find(t => t.tabId === activeTab)) {
      setActiveTab(tabId);
    }
  };

  const renameTab = (tabId, newName) => {
    const updatedTabs = tabs.map(t => 
      t.tabId === tabId 
        ? { ...t, customName: newName.trim() || null }
        : t
    );
    setTabs(updatedTabs);
  };

  const duplicateTab = (tabId) => {
    const tabToDuplicate = tabs.find(t => t.tabId === tabId);
    if (tabToDuplicate) {
      const newTab = {
        ...tabToDuplicate,
        tabId: `${tabToDuplicate.id}-${Date.now()}`,
        customName: tabToDuplicate.customName ? `${tabToDuplicate.customName} (Copy)` : null,
        data: { ...tabToDuplicate.data }
      };
      const tabIndex = tabs.findIndex(t => t.tabId === tabId);
      const newTabs = [...tabs.slice(0, tabIndex + 1), newTab, ...tabs.slice(tabIndex + 1)];
      setTabs(newTabs);
      setActiveTab(newTab.tabId);
    }
  };

  const handleSaveCurrentTab = () => {
    const currentTab = tabs.find(t => t.tabId === activeTab);
    if (currentTab) {
      setTabToSave(currentTab);
      setShowSaveDialog(true);
    } else {
      toast.error('No active tab to save');
    }
  };

  const handleOpenSavedItem = (savedItem) => {
    // Check if this saved item is already open
    const existingTab = tabs.find(t => t.savedItemId === savedItem.id);
    if (existingTab) {
      // Switch to existing tab instead of opening new one
      setActiveTab(existingTab.tabId);
      toast.success(`Switched to: ${savedItem.name}`);
      return;
    }

    // Find the tool definition
    const tool = TOOLS.find(t => t.id === savedItem.tool_id);
    if (!tool) {
      toast.error('Tool not found');
      return;
    }

    // Create a new tab with saved data and savedItemId
    const newTab = {
      tabId: `saved-${savedItem.id}-${Date.now()}`,
      ...tool,
      customName: savedItem.name,
      data: savedItem.tool_data || {},
      savedItemId: savedItem.id // Mark this tab as opened from collection
    };
    setTabs([...tabs, newTab]);
    setActiveTab(newTab.tabId);
    toast.success(`Opened: ${savedItem.name}`);
  };

  const filteredTools = searchQuery
    ? TOOLS.filter(tool => 
        tool.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        tool.description.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : TOOLS;

  const categoryTools = selectedCategory
    ? TOOLS.filter(tool => {
        const matchesCategory = tool.category === selectedCategory.id;
        const matchesSearch = !searchQuery || 
          tool.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          tool.description.toLowerCase().includes(searchQuery.toLowerCase());
        return matchesCategory && matchesSearch;
      })
    : [];

  const favoriteTools = TOOLS.filter(tool => favorites.includes(tool.id));

  const filteredCategories = searchQuery
    ? CATEGORIES.filter(cat =>
        cat.name.toLowerCase().includes(searchQuery.toLowerCase())
      )
    : CATEGORIES;

  return (
    <div className="App" data-testid="productivity-app">
      <Toaster position="top-right" richColors />
      
      {/* Top Bar */}
      <div className="top-bar" data-testid="top-bar">
        <div className="flex items-center gap-3">
          <Code className="w-6 h-6" />
          <span className="text-lg font-semibold">Devvy Studio</span>
        </div>
        <div className="flex items-center gap-3">
          {activeTab && (
            <Button 
              variant="ghost" 
              size="icon"
              onClick={handleSaveCurrentTab}
              data-testid="save-tab-button"
              title="Save to Collection"
            >
              <Save className="w-5 h-5 text-gray-400 hover:text-emerald-500" />
            </Button>
          )}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-gray-800/50">
            <User className="w-4 h-4" />
            <span className="text-sm">Desktop User</span>
          </div>
        </div>
      </div>

      <div className="main-container">
        {/* Two-Pane Sidebar */}
        <div className={`sidebar ${isSidebarCollapsed ? 'collapsed' : ''}`} data-testid="sidebar">
          {/* First Level - Icon Pane */}
          <div className="icon-pane">
            <button
              className={`icon-pane-item ${activePane === 'categories' ? 'active' : ''}`}
              onClick={() => {
                setActivePane('categories');
                setSelectedCategory(null);
                setSearchQuery('');
                setIsSidebarCollapsed(false);
              }}
              title="Categories"
              data-testid="icon-categories"
            >
              <Menu className="w-5 h-5" />
            </button>
            <button
              className={`icon-pane-item ${activePane === 'tools' ? 'active' : ''}`}
              onClick={() => {
                setActivePane('tools');
                setSelectedCategory(null);
                setSearchQuery('');
                setIsSidebarCollapsed(false);
              }}
              title="All Tools"
              data-testid="icon-tools"
            >
              <Search className="w-5 h-5" />
            </button>
            <button
              className={`icon-pane-item ${activePane === 'collections' ? 'active' : ''}`}
              onClick={() => {
                setActivePane('collections');
                setSelectedCategory(null);
                setSearchQuery('');
                setIsSidebarCollapsed(false);
              }}
              title="Collections"
              data-testid="icon-collections"
            >
              <Bookmark className="w-5 h-5" />
            </button>
            {favorites.length > 0 && (
              <button
                className={`icon-pane-item ${activePane === 'favorites' ? 'active' : ''}`}
                onClick={() => {
                  setActivePane('favorites');
                  setSelectedCategory(null);
                  setSearchQuery('');
                  setIsSidebarCollapsed(false);
                }}
                title="Favorites"
                data-testid="icon-favorites"
              >
                <Star className="w-5 h-5" />
              </button>
            )}
          </div>

          {/* Second Level - Content Pane */}
          <div className="content-pane">
            {/* Collapse Toggle */}
            <button
              onClick={toggleSidebar}
              className="sidebar-toggle"
              title={isSidebarCollapsed ? "Expand Sidebar" : "Collapse Sidebar"}
            >
              <ChevronRight className={`w-3 h-3 transition-transform ${isSidebarCollapsed ? '' : 'rotate-180'}`} />
            </button>
            
            {activePane !== 'collections' && (
              <div className="content-pane-header">
                <div className="content-pane-title">
                  {activePane === 'categories' && !selectedCategory && 'Categories'}
                  {activePane === 'categories' && selectedCategory && (
                    <div className="flex items-center gap-2">
                      <button
                        onClick={handleBackToCategories}
                        className="text-gray-400 hover:text-white"
                        data-testid="back-to-categories"
                      >
                        <ChevronRight className="w-4 h-4 rotate-180" />
                      </button>
                      {selectedCategory.name} Tools
                    </div>
                  )}
                  {activePane === 'tools' && 'All Tools'}
                  {activePane === 'favorites' && 'Favorites'}
                </div>
                <Input
                  placeholder={
                    activePane === 'categories' && selectedCategory
                      ? `Search ${selectedCategory.name} tools...`
                      : `Search ${activePane}...`
                  }
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="search-input"
                  data-testid="pane-search-input"
                />
              </div>
            )}

            <div className={`content-pane-body ${activePane !== 'collections' ? 'grid-layout' : ''}`}>
              {/* Show Collections Panel */}
              {activePane === 'collections' && (
                <CollectionsPanel onOpenItem={handleOpenSavedItem} />
              )}
              {/* Show Categories */}
              {activePane === 'categories' && !selectedCategory && (
                <>
                  {filteredCategories.map((category) => {
                    const Icon = category.icon;
                    return (
                      <button
                        key={category.id}
                        className="pane-item"
                        data-category={category.id}
                        onClick={() => handleCategorySelect(category)}
                        data-testid={`pane-category-${category.id}`}
                      >
                        <div className="pane-item-icon">
                          <Icon className="w-6 h-6" />
                        </div>
                        <div className="pane-item-content">
                          <div className="pane-item-name">{category.name}</div>
                          <div className="pane-item-desc">
                            {TOOLS.filter(t => t.category === category.id).length} tools
                          </div>
                        </div>
                      </button>
                    );
                  })}
                </>
              )}

              {/* Show Tools in Selected Category */}
              {activePane === 'categories' && selectedCategory && (
                <>
                  {categoryTools.map((tool) => (
                    <ToolPaneItem
                      key={tool.id}
                      tool={tool}
                      onOpen={openTool}
                      isFavorite={favorites.includes(tool.id)}
                      onToggleFavorite={toggleFavorite}
                      isPremium={toolsConfig[tool.id]?.is_premium}
                    />
                  ))}
                </>
              )}

              {/* Show All Tools */}
              {activePane === 'tools' && (
                <>
                  {filteredTools.map((tool) => (
                    <ToolPaneItem
                      key={tool.id}
                      tool={tool}
                      onOpen={openTool}
                      isFavorite={favorites.includes(tool.id)}
                      onToggleFavorite={toggleFavorite}
                      isPremium={toolsConfig[tool.id]?.is_premium}
                    />
                  ))}
                </>
              )}

              {/* Show Favorites */}
              {activePane === 'favorites' && (
                <>
                  {favoriteTools.map((tool) => (
                    <ToolPaneItem
                      key={tool.id}
                      tool={tool}
                      onOpen={openTool}
                      isFavorite={true}
                      onToggleFavorite={toggleFavorite}
                      isPremium={toolsConfig[tool.id]?.is_premium}
                    />
                  ))}
                </>
              )}
            </div>
          </div>
        </div>

        {/* Main Content */}
        <div className="content-area">
          {/* Tab Bar */}
          {tabs.length > 0 && (
            <div className="tab-bar" data-testid="tab-bar">
              {tabs.map((tab) => (
                <TabItem
                  key={tab.tabId}
                  tab={tab}
                  isActive={activeTab === tab.tabId}
                  onActivate={() => setActiveTab(tab.tabId)}
                  onClose={(e) => closeTab(tab.tabId, e)}
                  onRename={(newName) => renameTab(tab.tabId, newName)}
                  onDuplicate={() => duplicateTab(tab.tabId)}
                  onCloseOthers={() => closeOtherTabs(tab.tabId)}
                  onCloseToRight={() => closeTabsToRight(tab.tabId)}
                />
              ))}
            </div>
          )}

          {/* Tool Content */}
          <div className="tool-content">
            {tabs.map((tab) => (
              <div
                key={tab.tabId}
                style={{ display: activeTab === tab.tabId ? 'block' : 'none' }}
              >
                {tab.id === 'json-beautifier' && (
                  <JSONBeautifierTool tab={tab} tabs={tabs} setTabs={setTabs} />
                )}
                {tab.id === 'json-validator' && (
                  <JSONValidatorTool tab={tab} tabs={tabs} setTabs={setTabs} />
                )}
                {tab.id === 'api-tester' && (
                  <RestApiTester tab={tab} tabs={tabs} setTabs={setTabs} />
                )}
                {tab.id === 'grpc-tester' && (
                  <GrpcTester tab={tab} tabs={tabs} setTabs={setTabs} />
                )}
                {tab.id === 'ui-recorder' && (
                  <UiRecorder tab={tab} tabs={tabs} setTabs={setTabs} />
                )}
              </div>
            ))}

            {tabs.length === 0 && (
              <div className="empty-state" data-testid="empty-state">
                <Code className="w-24 h-24 mb-6 opacity-30" />
                <h2 className="text-2xl font-semibold mb-2">Welcome to Devvy Studio</h2>
                <p className="text-gray-400 mb-6">Select a tool from the sidebar to get started</p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Save to Collection Dialog */}
      {showSaveDialog && tabToSave && (
        <SaveToCollectionDialog
          open={showSaveDialog}
          onClose={() => {
            setShowSaveDialog(false);
            setTabToSave(null);
          }}
          tab={tabToSave}
        />
      )}
    </div>
  );
}

function JSONValidatorTool({ tab, tabs, setTabs }) {
  const [inputJSON, setInputJSON] = useState(tab.data.input || '');
  const [isValid, setIsValid] = useState(tab.data.isValid !== undefined ? tab.data.isValid : null);
  const [error, setError] = useState(tab.data.error || null);

  const validateJSON = async () => {
    if (!inputJSON.trim()) {
      setIsValid(null);
      setError(null);
      return;
    }

    try {
      const response = await axios.post(`${API}/validate`, {
        json_string: inputJSON
      });

      setIsValid(response.data.valid);
      setError(response.data.error);

      // Update tab data
      const updatedTabs = tabs.map(t =>
        t.tabId === tab.tabId
          ? { ...t, data: { input: inputJSON, isValid: response.data.valid, error: response.data.error } }
          : t
      );
      setTabs(updatedTabs);

      if (response.data.valid) {
        toast.success('Valid JSON!');
      } else {
        toast.error('Invalid JSON');
      }
    } catch (err) {
      console.error('Validation error:', err);
      toast.error('Failed to validate JSON');
    }
  };

  return (
    <div className="json-tool" data-testid="json-validator">
      <div className="json-panel">
        <div className="panel-header">
          <h3>Input JSON</h3>
          <Button
            onClick={validateJSON}
            size="sm"
            data-testid="validate-button"
          >
            <Check className="w-4 h-4 mr-2" />
            Validate
          </Button>
        </div>
        <div className="editor-container">
          <Editor
            height="100%"
            defaultLanguage="json"
            theme="vs-dark"
            value={inputJSON}
            onChange={(value) => setInputJSON(value || '')}
            options={{
              minimap: { enabled: false },
              fontSize: 14,
              lineNumbers: 'on',
              scrollBeyondLastLine: false,
              automaticLayout: true,
              tabSize: 2,
            }}
          />
        </div>
      </div>

      <div className="json-panel">
        <div className="panel-header">
          <h3>Validation Result</h3>
        </div>
        <div className="p-4 h-full bg-[#1e1e1e] text-white overflow-auto font-mono text-sm">
          {isValid === true && (
            <div className="flex flex-col items-center justify-center h-full text-emerald-500">
              <Check className="w-16 h-16 mb-4" />
              <p className="text-xl">Valid JSON</p>
            </div>
          )}
          {isValid === false && (
            <div className="text-red-400">
              <div className="flex items-center gap-2 mb-4">
                <AlertCircle className="w-6 h-6" />
                <span className="text-lg font-semibold">Invalid JSON</span>
              </div>
              <div className="bg-red-900/20 p-4 rounded-lg border border-red-900/50 whitespace-pre-wrap break-words">
                {error}
              </div>
            </div>
          )}
          {isValid === null && (
            <div className="flex flex-col items-center justify-center h-full text-gray-500">
              <p>Enter JSON and click Validate</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function TabItem({ tab, isActive, onActivate, onClose, onRename, onDuplicate, onCloseOthers, onCloseToRight }) {
  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState('');
  const [showContextMenu, setShowContextMenu] = useState(false);
  const [contextMenuPos, setContextMenuPos] = useState({ x: 0, y: 0 });
  const inputRef = useRef(null);

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  const handleDoubleClick = (e) => {
    e.stopPropagation();
    setEditName(tab.customName || tab.name);
    setIsEditing(true);
  };

  const handleRename = () => {
    if (editName.trim()) {
      onRename(editName);
    }
    setIsEditing(false);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      handleRename();
    } else if (e.key === 'Escape') {
      setIsEditing(false);
    }
  };

  const handleContextMenu = (e) => {
    e.preventDefault();
    setContextMenuPos({ x: e.clientX, y: e.clientY });
    setShowContextMenu(true);
  };

  useEffect(() => {
    const handleClickOutside = () => setShowContextMenu(false);
    if (showContextMenu) {
      document.addEventListener('click', handleClickOutside);
      return () => document.removeEventListener('click', handleClickOutside);
    }
  }, [showContextMenu]);

  return (
    <>
      <div
        className={`tab ${isActive ? 'active' : ''}`}
        onClick={onActivate}
        onContextMenu={handleContextMenu}
        data-testid={`tab-${tab.tabId}`}
      >
        <tab.icon className="w-4 h-4 flex-shrink-0" />
        {isEditing ? (
          <input
            ref={inputRef}
            type="text"
            value={editName}
            onChange={(e) => setEditName(e.target.value)}
            onBlur={handleRename}
            onKeyDown={handleKeyDown}
            className="tab-name-input"
            onClick={(e) => e.stopPropagation()}
            data-testid={`tab-rename-input-${tab.tabId}`}
          />
        ) : (
          <span 
            onDoubleClick={handleDoubleClick}
            className="tab-name"
            title={tab.customName || tab.name}
          >
            {tab.customName || tab.name}
          </span>
        )}
        <button
          className="tab-close"
          onClick={onClose}
          data-testid={`close-tab-${tab.tabId}`}
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {showContextMenu && (
        <div 
          className="context-menu"
          style={{ 
            position: 'fixed', 
            top: contextMenuPos.y, 
            left: contextMenuPos.x,
            zIndex: 1000
          }}
          data-testid={`context-menu-${tab.tabId}`}
        >
          <button 
            className="context-menu-item"
            onClick={() => {
              setEditName(tab.customName || tab.name);
              setIsEditing(true);
              setShowContextMenu(false);
            }}
            data-testid="context-menu-rename"
          >
            Rename Tab
          </button>
          <button 
            className="context-menu-item"
            onClick={() => {
              onDuplicate();
              setShowContextMenu(false);
            }}
            data-testid="context-menu-duplicate"
          >
            Duplicate Tab
          </button>
          <div className="context-menu-divider" />
          <button 
            className="context-menu-item"
            onClick={() => {
              onClose();
              setShowContextMenu(false);
            }}
            data-testid="context-menu-close"
          >
            Close
          </button>
          <button 
            className="context-menu-item"
            onClick={() => {
              onCloseOthers();
              setShowContextMenu(false);
            }}
            data-testid="context-menu-close-others"
          >
            Close Others
          </button>
          <button 
            className="context-menu-item"
            onClick={() => {
              onCloseToRight();
              setShowContextMenu(false);
            }}
            data-testid="context-menu-close-right"
          >
            Close to the Right
          </button>
        </div>
      )}
    </>
  );
}

function ToolPaneItem({ tool, onOpen, isFavorite, onToggleFavorite, isPremium }) {
  const Icon = tool.icon;
  
  return (
    <button
      className="pane-item"
      data-category={tool.category}
      onClick={() => onOpen(tool)}
      data-testid={`tool-pane-item-${tool.id}`}
    >
      <div className="pane-item-icon">
        <Icon className="w-6 h-6" />
      </div>
      <div className="pane-item-content">
        <div className="pane-item-name">
          {tool.name}
          {isPremium && <Crown className="w-3 h-3 text-amber-500 inline ml-1" />}
        </div>
      </div>
      {isFavorite && (
        <Star className="w-3 h-3 text-amber-500 absolute top-2 right-2" fill="currentColor" />
      )}
    </button>
  );
}

function JSONBeautifierTool({ tab, tabs, setTabs }) {
  const [inputJSON, setInputJSON] = useState(tab.data.input || '');
  const [outputJSON, setOutputJSON] = useState(tab.data.output || '');
  const [isValid, setIsValid] = useState(true);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);

  const beautifyJSON = async () => {
    try {
      const response = await axios.post(`${API}/beautify`, {
        json_string: inputJSON,
        indent: 2
      });

      setOutputJSON(response.data.beautified);
      setIsValid(response.data.valid);
      setError(response.data.error);

      // Update tab data
      const updatedTabs = tabs.map(t => 
        t.tabId === tab.tabId 
          ? { ...t, data: { input: inputJSON, output: response.data.beautified } }
          : t
      );
      setTabs(updatedTabs);

      if (response.data.valid) {
        toast.success('JSON beautified successfully!');
      } else {
        toast.error('Invalid JSON format');
      }
    } catch (err) {
      console.error('Beautify error:', err);
      toast.error('Failed to beautify JSON');
    }
  };

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(outputJSON);
      setCopied(true);
      toast.success('Copied to clipboard!');
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Copy error:', err);
      toast.error('Failed to copy');
    }
  };

  return (
    <div className="json-tool" data-testid="json-beautifier">
      <div className="json-panel">
        <div className="panel-header">
          <h3>Input JSON</h3>
          <Button 
            onClick={beautifyJSON} 
            size="sm"
            data-testid="beautify-button"
          >
            <Code className="w-4 h-4 mr-2" />
            Beautify
          </Button>
        </div>
        <div className="editor-container">
          <Editor
            height="100%"
            defaultLanguage="json"
            theme="vs-dark"
            value={inputJSON}
            onChange={(value) => setInputJSON(value || '')}
            options={{
              minimap: { enabled: false },
              fontSize: 14,
              lineNumbers: 'on',
              scrollBeyondLastLine: false,
              automaticLayout: true,
              tabSize: 2,
            }}
          />
        </div>
      </div>

      <div className="json-panel">
        <div className="panel-header">
          <div className="flex items-center gap-2">
            <h3>Output</h3>
            {!isValid && error && (
              <span className="text-xs text-red-400 flex items-center gap-1">
                <AlertCircle className="w-3 h-3" />
                {error}
              </span>
            )}
          </div>
          <Button 
            onClick={copyToClipboard}
            size="sm"
            variant="outline"
            disabled={!outputJSON}
            data-testid="copy-button"
          >
            {copied ? (
              <><Check className="w-4 h-4 mr-2" /> Copied</>
            ) : (
              <><Copy className="w-4 h-4 mr-2" /> Copy</>
            )}
          </Button>
        </div>
        <div className="editor-container">
          <Editor
            height="100%"
            defaultLanguage="json"
            theme="vs-dark"
            value={outputJSON}
            options={{
              minimap: { enabled: false },
              fontSize: 14,
              lineNumbers: 'on',
              scrollBeyondLastLine: false,
              readOnly: true,
              automaticLayout: true,
              tabSize: 2,
            }}
          />
        </div>
      </div>
    </div>
  );
}

// Main App with Auth Provider
export default function App() {
  return (
    <AuthProvider>
      <AuthWrapper />
    </AuthProvider>
  );
}

function AuthWrapper() {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="loading-screen">
        <Code className="w-16 h-16 animate-pulse text-emerald-500" />
        <p className="mt-4 text-gray-400">Loading...</p>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <AuthScreen />;
  }

  return <MainApp />;
}