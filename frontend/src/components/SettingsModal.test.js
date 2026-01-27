import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import '@testing-library/jest-dom';
import SettingsModal from './SettingsModal';

// Mock dependencies
jest.mock('lucide-react', () => ({
  X: () => <svg data-testid="icon-x" />,
  Palette: () => <svg />,
  Check: () => <svg />,
  Settings: () => <svg />,
  Bell: () => <svg />,
  Shield: () => <svg />,
  Database: () => <svg />,
  Server: () => <svg />,
  Plus: () => <svg />,
  Trash2: () => <svg data-testid="icon-trash" />,
  Edit2: () => <svg data-testid="icon-edit" />,
  Save: () => <svg />,
}));

jest.mock('../themes', () => ({
  THEMES: {
    dark: { id: 'dark', type: 'dark', name: 'Dark', colors: {} }
  },
  getStoredTheme: () => 'dark',
  applyTheme: jest.fn(),
}));

jest.mock('sonner', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
  },
}));

jest.mock('./DataExportImport', () => () => <div>DataExportImport</div>);

// Mock localStorage
const localStorageMock = (function() {
  let store = {};
  return {
    getItem: function(key) {
      return store[key] || null;
    },
    setItem: function(key, value) {
      store[key] = value.toString();
    },
    clear: function() {
      store = {};
    },
    removeItem: function(key) {
      delete store[key];
    }
  };
})();

Object.defineProperty(window, 'localStorage', {
  value: localStorageMock
});

describe('SettingsModal Accessibility', () => {
  const defaultProps = {
    isOpen: true,
    onClose: jest.fn(),
    tabs: [],
    setTabs: jest.fn(),
    favorites: [],
    setFavorites: jest.fn(),
  };

  test('close button should have accessible name', () => {
    render(<SettingsModal {...defaultProps} />);
    const closeButton = screen.getByRole('button', { name: /close settings/i });
    expect(closeButton).toBeInTheDocument();
  });

  test('environment config buttons should have dynamic accessible names', () => {
    render(<SettingsModal {...defaultProps} />);

    // Switch to Environment tab
    const envTab = screen.getByText(/Environment/i);
    fireEvent.click(envTab);

    // Switch to Git Repositories
    const gitTab = screen.getByText(/Git Repositories/i);
    fireEvent.click(gitTab);

    // Add a new item
    const addButton = screen.getByText(/Add New/i);
    fireEvent.click(addButton);

    // Fill required fields
    const nameInput = screen.getByPlaceholderText('Name');
    fireEvent.change(nameInput, { target: { value: 'Test Repo' } });

    // Save the item
    const saveButton = screen.getByText('Save');
    fireEvent.click(saveButton);

    // Verify dynamic labels
    const editButton = screen.getByRole('button', { name: 'Edit Test Repo' });
    expect(editButton).toBeInTheDocument();

    const deleteButton = screen.getByRole('button', { name: 'Delete Test Repo' });
    expect(deleteButton).toBeInTheDocument();
  });
});
