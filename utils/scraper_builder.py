#!/usr/bin/env python3
import os
import json
import asyncio
import inspect
from typing import Dict, List, Any, Optional
import jinja2
from bs4 import BeautifulSoup
from playwright.async_api import Page

from utils.browser import BrowserClient
from utils.logger import get_logger

logger = get_logger('scraper_builder')

class ScraperBuilder(BrowserClient):
    """
    Interactive tool for building scrapers by selecting elements on a webpage.
    Extends the BrowserClient to add element selection and code generation functionality.
    """
    
    def __init__(self, source_id: str):
        """
        Initialize the scraper builder
        
        Args:
            source_id (str): Unique identifier for the source
        """
        super().__init__(headless=False)  # We need the browser to be visible for interaction
        self.source_id = source_id
        self.selections = {}
        self.base_url = None
        
    async def setup_interactive_mode(self, url: str):
        """
        Set up the browser for interactive element selection with a UI panel
        
        Args:
            url (str): URL to navigate to
        """
        # Start the browser if not already started
        if not self.page:
            await self.start()
            
        # Navigate to the URL
        await self.goto(url)
        self.base_url = url
        
        # Define the common fields that most scrapers will need
        common_fields = [
            "title", 
            "published_date", 
            "author", 
            "content",
            "claims"
        ]
        
        # Inject helper script to create UI and handle interactions
        await self.page.evaluate("""(commonFields) => {
            // Create styles for the UI and highlighting
            const style = document.createElement('style');
            style.innerHTML = `
                .scraper-builder-hover { 
                    outline: 2px solid blue !important; 
                    background-color: rgba(0, 0, 255, 0.1) !important; 
                }
                .scraper-builder-selected { 
                    outline: 2px solid green !important; 
                    background-color: rgba(0, 255, 0, 0.1) !important; 
                }
                .scraper-builder-multi-selected {
                    outline: 2px dashed green !important;
                    background-color: rgba(0, 255, 0, 0.05) !important;
                }
                #scraper-builder-panel {
                    position: fixed;
                    top: 10px;
                    right: 10px;
                    width: 300px;
                    background-color: white;
                    border: 1px solid #ccc;
                    border-radius: 5px;
                    box-shadow: 0 0 10px rgba(0,0,0,0.2);
                    z-index: 10000;
                    font-family: Arial, sans-serif;
                    padding: 10px;
                    max-height: 90vh;
                    overflow-y: auto;
                }
                #scraper-builder-panel h3 {
                    margin-top: 0;
                    padding-bottom: 8px;
                    border-bottom: 1px solid #eee;
                }
                #scraper-builder-panel .field-btn {
                    display: block;
                    width: 100%;
                    padding: 8px;
                    margin: 5px 0;
                    background-color: #f1f1f1;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                    cursor: pointer;
                    text-align: left;
                }
                #scraper-builder-panel .field-btn:hover {
                    background-color: #e9e9e9;
                }
                #scraper-builder-panel .field-btn.active {
                    background-color: #4CAF50;
                    color: white;
                }
                #scraper-builder-panel .field-btn.selected {
                    background-color: #2196F3;
                    color: white;
                }
                #scraper-builder-panel .panel-section {
                    margin-bottom: 15px;
                }
                #scraper-builder-panel .custom-field {
                    display: flex;
                    margin: 5px 0;
                }
                #scraper-builder-panel .custom-field input {
                    flex-grow: 1;
                    padding: 8px;
                    border: 1px solid #ddd;
                    border-radius: 4px 0 0 4px;
                }
                #scraper-builder-panel .custom-field button {
                    padding: 8px;
                    border: 1px solid #ddd;
                    border-left: none;
                    border-radius: 0 4px 4px 0;
                    background-color: #f1f1f1;
                    cursor: pointer;
                }
                #scraper-builder-panel .actions {
                    display: flex;
                    justify-content: space-between;
                }
                #scraper-builder-panel .actions button {
                    padding: 10px;
                    border: none;
                    border-radius: 4px;
                    cursor: pointer;
                }
                #scraper-builder-panel .actions .primary {
                    background-color: #4CAF50;
                    color: white;
                }
                #scraper-builder-panel .actions .secondary {
                    background-color: #f1f1f1;
                }
                #scraper-builder-panel .field-selections {
                    margin-top: 15px;
                    border-top: 1px solid #eee;
                    padding-top: 10px;
                }
                #scraper-builder-panel .field-item {
                    padding: 8px;
                    margin: 5px 0;
                    background-color: #f9f9f9;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                    position: relative;
                }
                #scraper-builder-panel .field-item .delete {
                    position: absolute;
                    right: 5px;
                    top: 5px;
                    color: #f44336;
                    cursor: pointer;
                    font-weight: bold;
                }
                #scraper-builder-panel .field-item .field-name {
                    font-weight: bold;
                }
                #scraper-builder-panel .field-item .field-sample {
                    font-size: 0.8em;
                    color: #666;
                    margin-top: 5px;
                    white-space: nowrap;
                    overflow: hidden;
                    text-overflow: ellipsis;
                }
                #scraper-builder-status {
                    position: fixed;
                    bottom: 10px;
                    left: 50%;
                    transform: translateX(-50%);
                    background-color: rgba(0,0,0,0.7);
                    color: white;
                    padding: 10px 20px;
                    border-radius: 20px;
                    font-family: Arial, sans-serif;
                    z-index: 10001;
                    display: none;
                }
            `;
            document.head.appendChild(style);
            
            // Create the UI panel
            const panel = document.createElement('div');
            panel.id = 'scraper-builder-panel';
            panel.innerHTML = `
                <h3>Scraper Builder</h3>
                <div class="panel-section">
                    <p>Select a field type, then click on elements in the page to extract.</p>
                    <div id="field-buttons">
                        ${commonFields.map(field => 
                            `<button class="field-btn" data-field="${field}">${field}</button>`
                        ).join('')}
                    </div>
                    <div class="custom-field">
                        <input type="text" id="custom-field-name" placeholder="Custom field name">
                        <button id="add-custom-field">Add</button>
                    </div>
                </div>
                <div class="panel-section">
                    <div>
                        <label>
                            <input type="checkbox" id="multi-select-mode"> Multi-select mode 
                            <small>(for content paragraphs)</small>
                        </label>
                    </div>
                </div>
                <div class="panel-section field-selections">
                    <h4>Selected Fields</h4>
                    <div id="selected-fields">
                        <p>No fields selected yet</p>
                    </div>
                </div>
                <div class="panel-section actions">
                    <button id="reset-btn" class="secondary">Reset All</button>
                    <button id="generate-btn" class="primary">Generate Scraper</button>
                </div>
            `;
            document.body.appendChild(panel);
            
            // Create status notification element
            const status = document.createElement('div');
            status.id = 'scraper-builder-status';
            document.body.appendChild(status);
            
            // Initialize application state
            window.scraperBuilder = {
                activeField: null,
                multiSelectMode: false,
                multiSelectedElements: [],
                selections: {},
                showStatus: function(message, duration = 3000) {
                    const status = document.getElementById('scraper-builder-status');
                    status.textContent = message;
                    status.style.display = 'block';
                    setTimeout(() => {
                        status.style.display = 'none';
                    }, duration);
                },
                updateSelectedFields: function() {
                    console.log("Updating selected fields display");
                    console.log("Current selections:", this.selections);
                    
                    const container = document.getElementById('selected-fields');
                    if (Object.keys(this.selections).length === 0) {
                        container.innerHTML = '<p>No fields selected yet</p>';
                        return;
                    }
                    
                    container.innerHTML = '';
                    for (const [field, data] of Object.entries(this.selections)) {
                        console.log(`Adding field ${field} to UI`);
                        const item = document.createElement('div');
                        item.className = 'field-item';
                        item.innerHTML = `
                            <span class="delete" data-field="${field}">×</span>
                            <div class="field-name">${field}</div>
                            <div class="field-sample">${data.sample_text}</div>
                        `;
                        container.appendChild(item);
                    }
                    
                    // Add event listeners to delete buttons
                    document.querySelectorAll('.field-item .delete').forEach(btn => {
                        btn.addEventListener('click', function() {
                            const field = this.getAttribute('data-field');
                            console.log(`Deleting field ${field}`);
                            
                            // Also remove highlighting from any elements selected for this field
                            document.querySelectorAll(`.scraper-builder-selected[data-field="${field}"]`).forEach(el => {
                                el.classList.remove('scraper-builder-selected');
                                el.removeAttribute('data-field');
                            });
                            
                            delete window.scraperBuilder.selections[field];
                            window.scraperBuilder.updateSelectedFields();
                        });
                    });
                }
            };
            
            // Track the current hovered element
            window.currentHoverElement = null;
            
            // Function to handle mouseover
            window.handleMouseOver = function(event) {
                if (!window.scraperBuilder.activeField) return;
                
                if (window.currentHoverElement) {
                    window.currentHoverElement.classList.remove('scraper-builder-hover');
                }
                event.target.classList.add('scraper-builder-hover');
                window.currentHoverElement = event.target;
                event.stopPropagation();
            };
            
            // Function to handle mouseout
            window.handleMouseOut = function(event) {
                event.target.classList.remove('scraper-builder-hover');
                window.currentHoverElement = null;
                event.stopPropagation();
            };
            
            // Function to handle clicks on page elements
            window.handleElementClick = function(event) {
                if (!window.scraperBuilder.activeField) return;
                
                // Prevent the click from activating links etc.
                event.preventDefault();
                event.stopPropagation();
                
                const targetElement = event.target;
                
                if (window.scraperBuilder.multiSelectMode) {
                    // Handle multi-select mode (for content paragraphs)
                    if (targetElement.classList.contains('scraper-builder-multi-selected')) {
                        // Deselect if already selected
                        targetElement.classList.remove('scraper-builder-multi-selected');
                        window.scraperBuilder.multiSelectedElements = 
                            window.scraperBuilder.multiSelectedElements.filter(el => el !== targetElement);
                    } else {
                        // Add to selection
                        targetElement.classList.add('scraper-builder-multi-selected');
                        window.scraperBuilder.multiSelectedElements.push(targetElement);
                    }
                    
                    // If we have selected elements, update the field data
                    if (window.scraperBuilder.multiSelectedElements.length > 0) {
                        // Generate a CSS selector that matches all selected elements
                        // This is a simplified approach - in a real app we'd need more robust selector generation
                        const field = window.scraperBuilder.activeField;
                        const elements = window.scraperBuilder.multiSelectedElements;
                        
                        // For simplicity, use the tag name of the first element
                        const tagName = elements[0].tagName.toLowerCase();
                        const selector = tagName;
                        
                        // Extract text from all selected elements
                        const texts = elements.map(el => el.textContent.trim());
                        const sampleText = texts.join(' ').substring(0, 100) + (texts.join(' ').length > 100 ? '...' : '');
                        
                        // Store the selection data
                        window.scraperBuilder.selections[field] = {
                            selector_type: 'css',
                            selector: selector,
                            sample_text: sampleText,
                            is_multi: true,
                            multi_count: elements.length
                        };
                        
                        // Update UI
                        window.scraperBuilder.updateSelectedFields();
                        window.scraperBuilder.showStatus(`Updated ${field} with ${elements.length} elements`);
                    }
                } else {
                    // Handle single element selection
                    // Remove previous selection highlight for this field only
                    document.querySelectorAll('.scraper-builder-selected').forEach(el => {
                        if (el.getAttribute('data-field') === window.scraperBuilder.activeField) {
                            el.classList.remove('scraper-builder-selected');
                            el.removeAttribute('data-field');
                        }
                    });
                    
                    // Highlight the clicked element and mark it with the field
                    targetElement.classList.add('scraper-builder-selected');
                    targetElement.setAttribute('data-field', window.scraperBuilder.activeField);
                    
                    // Generate CSS selector for the element
                    const selector = getCssSelector(targetElement);
                    const field = window.scraperBuilder.activeField;
                    const sampleText = targetElement.textContent.trim().substring(0, 100) + 
                                       (targetElement.textContent.trim().length > 100 ? '...' : '');
                    
                    console.log(`Selecting element for field: ${field}`);
                    
                    // Store the selection
                    window.scraperBuilder.selections[field] = {
                        selector_type: 'css',
                        selector: selector,
                        sample_text: sampleText,
                        is_multi: false
                    };
                    
                    // Update UI
                    window.scraperBuilder.updateSelectedFields();
                    window.scraperBuilder.showStatus(`Selected element for ${field}`);
                }
                
                return false;
            };
            
            // Function to generate a CSS selector for an element
            function getCssSelector(el) {
                if (el.id) {
                    return '#' + el.id;
                }
                
                // Try to get a unique selector using classes
                if (el.className) {
                    const classes = el.className.split(/\\s+/).filter(c => c && 
                        !c.includes('scraper-builder'));
                    for (const cls of classes) {
                        const selector = '.' + cls;
                        if (document.querySelectorAll(selector).length === 1) {
                            return selector;
                        }
                    }
                }
                
                // Get the element's tag name
                let path = el.tagName.toLowerCase();
                
                // If no unique identifier, traverse up the DOM
                let current = el;
                let i = 0;
                const max_iterations = 10; // Prevent infinite loops
                
                while (current.parentElement && i < max_iterations) {
                    // Find the index of the current element among siblings
                    let index = 1;
                    let sibling = current;
                    
                    while (sibling.previousElementSibling) {
                        sibling = sibling.previousElementSibling;
                        if (sibling.tagName === current.tagName) {
                            index++;
                        }
                    }
                    
                    // Build the selector
                    path = `${current.tagName.toLowerCase()}:nth-of-type(${index}) > ${path}`;
                    
                    // Check if this selector is unique
                    if (document.querySelectorAll(`${current.parentElement.tagName.toLowerCase()} > ${path}`).length === 1) {
                        return `${current.parentElement.tagName.toLowerCase()} > ${path}`;
                    }
                    
                    current = current.parentElement;
                    i++;
                }
                
                return path;
            }
            
            // Set up event listeners for the UI panel
            
            // Field selection buttons
            document.querySelectorAll('.field-btn').forEach(btn => {
                btn.addEventListener('click', function() {
                    const field = this.getAttribute('data-field');
                    console.log(`Field button clicked: ${field}`);
                    
                    // Deactivate all buttons
                    document.querySelectorAll('.field-btn').forEach(b => 
                        b.classList.remove('active'));
                    
                    // If clicking the active field, deactivate it
                    if (window.scraperBuilder.activeField === field) {
                        console.log(`Deactivating field: ${field}`);
                        window.scraperBuilder.activeField = null;
                        return;
                    }
                    
                    // Activate this button
                    this.classList.add('active');
                    window.scraperBuilder.activeField = field;
                    console.log(`Activated field: ${field}`);
                    window.scraperBuilder.showStatus(`Click on the ${field} element in the page`, 3000);
                });
            });
            
            // Custom field button
            document.getElementById('add-custom-field').addEventListener('click', function() {
                const input = document.getElementById('custom-field-name');
                const fieldName = input.value.trim();
                
                if (fieldName) {
                    // Create new button for this field
                    const btn = document.createElement('button');
                    btn.className = 'field-btn';
                    btn.setAttribute('data-field', fieldName);
                    btn.textContent = fieldName;
                    
                    // Add same event listener as other buttons
                    btn.addEventListener('click', function() {
                        const field = this.getAttribute('data-field');
                        
                        // Deactivate all buttons
                        document.querySelectorAll('.field-btn').forEach(b => 
                            b.classList.remove('active'));
                        
                        // If clicking the active field, deactivate it
                        if (window.scraperBuilder.activeField === field) {
                            window.scraperBuilder.activeField = null;
                            return;
                        }
                        
                        // Activate this button
                        this.classList.add('active');
                        window.scraperBuilder.activeField = field;
                        window.scraperBuilder.showStatus(`Click on the ${field} element in the page`);
                    });
                    
                    document.getElementById('field-buttons').appendChild(btn);
                    input.value = '';
                    
                    // Activate the new field
                    window.scraperBuilder.activeField = fieldName;
                    btn.classList.add('active');
                    window.scraperBuilder.showStatus(`Click on the ${fieldName} element in the page`);
                }
            });
            
            // Multi-select mode toggle
            document.getElementById('multi-select-mode').addEventListener('change', function() {
                window.scraperBuilder.multiSelectMode = this.checked;
                
                // Clear multi-selections when toggling off
                if (!this.checked) {
                    window.scraperBuilder.multiSelectedElements.forEach(el => {
                        el.classList.remove('scraper-builder-multi-selected');
                    });
                    window.scraperBuilder.multiSelectedElements = [];
                }
                
                window.scraperBuilder.showStatus(
                    this.checked ? 
                    'Multi-select mode enabled - click multiple elements' : 
                    'Single element selection mode'
                );
            });
            
            // Reset button
            document.getElementById('reset-btn').addEventListener('click', function() {
                // Clear all selections
                document.querySelectorAll('.scraper-builder-selected, .scraper-builder-multi-selected').forEach(el => {
                    el.classList.remove('scraper-builder-selected');
                    el.classList.remove('scraper-builder-multi-selected');
                });
                
                // Reset state
                window.scraperBuilder.activeField = null;
                window.scraperBuilder.multiSelectedElements = [];
                window.scraperBuilder.selections = {};
                
                // Deactivate all buttons
                document.querySelectorAll('.field-btn').forEach(b => 
                    b.classList.remove('active'));
                
                // Reset UI
                window.scraperBuilder.updateSelectedFields();
                window.scraperBuilder.showStatus('All selections reset');
            });
            
            // Generate button
            document.getElementById('generate-btn').addEventListener('click', function() {
                console.log('Generate button clicked');
                
                // Check if we have selections
                if (Object.keys(window.scraperBuilder.selections).length === 0) {
                    window.scraperBuilder.showStatus('Please select at least one field before generating', 3000);
                    console.log('No selections found');
                    return;
                }
                
                // Disable the generate button to prevent double-clicks
                this.disabled = true;
                this.textContent = 'Generating...';
                
                // Signal that we're ready to generate
                window.scraperBuilder.showStatus('Generating scraper...', 10000);
                console.log('Selections for generation:', JSON.stringify(window.scraperBuilder.selections));
                
                // Store the selections in a global variable as a fallback
                window.finalSelections = JSON.parse(JSON.stringify(window.scraperBuilder.selections));
                
                try {
                    // Use a custom event to signal we're done selecting
                    const event = new CustomEvent('scraper-builder-generate', {
                        detail: window.scraperBuilder.selections
                    });
                    document.dispatchEvent(event);
                    console.log('Generated event dispatched');
                    
                    // Add a fallback for browser compatibility
                    setTimeout(() => {
                        // Create a hidden input with the selections data
                        const input = document.createElement('input');
                        input.type = 'hidden';
                        input.id = 'scraper-builder-data';
                        input.value = JSON.stringify(window.scraperBuilder.selections);
                        document.body.appendChild(input);
                        console.log('Added fallback data element to body');
                    }, 100);
                    
                } catch (e) {
                    console.error('Error dispatching event:', e);
                    window.scraperBuilder.showStatus('Error generating scraper. Check console.', 5000);
                }
            });
            
            // Add event listeners to all elements in the page
            document.querySelectorAll('*').forEach(element => {
                // Skip elements in our UI
                if (element.closest('#scraper-builder-panel') || 
                    element.closest('#scraper-builder-status')) {
                    return;
                }
                
                element.addEventListener('mouseover', window.handleMouseOver, true);
                element.addEventListener('mouseout', window.handleMouseOut, true);
                element.addEventListener('click', window.handleElementClick, true);
            });
            
            window.scraperBuilder.showStatus('Scraper Builder initialized. Select a field to begin.', 5000);
        }""", common_fields)
        
        logger.info(f"Browser ready for interactive selection at {url}")
        logger.info("Use the panel in the browser to select elements and generate your scraper")
        
    async def wait_for_selections(self):
        """
        Wait for the user to complete their selections and click the generate button
        
        Returns:
            dict: The selected elements
        """
        # Log that we're waiting for selections
        logger.info("Waiting for user to make selections and click Generate...")
        
        # Set up a promise that will resolve when the user clicks the generate button
        # with multiple fallback mechanisms to ensure we get the data
        selections = await self.page.evaluate_handle("""() => {
            console.log("Setting up event listener for scraper-builder-generate");
            return new Promise(resolve => {
                // First mechanism: Listen for the custom event
                document.addEventListener('scraper-builder-generate', (event) => {
                    console.log("Generate event received with data:", event.detail);
                    if (event.detail && Object.keys(event.detail).length > 0) {
                        resolve(event.detail);
                        return;
                    }
                });
                
                // Second mechanism: Watch the global variable 
                let checkInterval = setInterval(() => {
                    if (window.finalSelections && Object.keys(window.finalSelections).length > 0) {
                        console.log("Found global finalSelections variable:", window.finalSelections);
                        clearInterval(checkInterval);
                        resolve(window.finalSelections);
                        return;
                    }
                }, 500);
                
                // Third mechanism: Watch for the hidden input element
                let dataElementInterval = setInterval(() => {
                    const dataElement = document.getElementById('scraper-builder-data');
                    if (dataElement && dataElement.value) {
                        console.log("Found data element with value");
                        clearInterval(dataElementInterval);
                        try {
                            const data = JSON.parse(dataElement.value);
                            if (data && Object.keys(data).length > 0) {
                                resolve(data);
                                return;
                            }
                        } catch (e) {
                            console.error("Error parsing data element value:", e);
                        }
                    }
                }, 500);
                
                // Fourth mechanism: Direct access to scraperBuilder.selections
                document.getElementById('generate-btn').addEventListener('click', () => {
                    console.log("Generate button clicked directly");
                    setTimeout(() => {
                        if (window.scraperBuilder && 
                            window.scraperBuilder.selections && 
                            Object.keys(window.scraperBuilder.selections).length > 0) {
                            
                            console.log("Accessing window.scraperBuilder.selections directly:", 
                                window.scraperBuilder.selections);
                            resolve(window.scraperBuilder.selections);
                            return;
                        }
                    }, 1000);
                });
                
                // Safety timeout after 2 minutes
                setTimeout(() => {
                    console.log("Timeout reached, resolving with any available selections");
                    if (window.scraperBuilder && window.scraperBuilder.selections) {
                        resolve(window.scraperBuilder.selections);
                    } else {
                        resolve({});
                    }
                }, 120000);
            });
        }""")
        
        try:
            # Convert to Python dict
            result = await selections.json_value()
            
            if not result or len(result) == 0:
                logger.warning("No selections received. Trying alternative method...")
                
                # Fallback: Get the selections directly from the page
                result = await self.page.evaluate("""() => {
                    console.log("Executing fallback selection retrieval");
                    return window.scraperBuilder ? window.scraperBuilder.selections : {};
                }""")
            
            logger.info(f"Received selections: {len(result)} fields")
            
            # Print the selections for debugging
            for field, data in result.items():
                logger.info(f"Field: {field}, Selector: {data.get('selector')}")
                
            return result
        except Exception as e:
            logger.error(f"Error retrieving selections: {e}")
            # Last resort fallback
            empty_result = {}
            logger.warning("Using empty result as fallback")
            return empty_result
        
    async def process_ui_selections(self, selections):
        """
        Process the selections from the UI and format them for the scraper
        
        Args:
            selections (dict): The selections from the UI
            
        Returns:
            dict: Processed selections ready for the scraper
        """
        processed_selections = {}
        
        for field, data in selections.items():
            # For multi-selected elements (like content paragraphs), handle specially
            if data.get('is_multi', False):
                # Create a version for content_paragraphs if this is content
                if field == 'content':
                    # Find all elements that match the selector
                    elements = await self.page.query_selector_all(data['selector'])
                    
                    # Get text from each element
                    texts = []
                    for element in elements:
                        text = await element.text_content()
                        texts.append(text.strip())
                    
                    # Store as content_paragraphs
                    processed_selections['content_paragraphs'] = {
                        'selector': data['selector'],
                        'selector_type': data['selector_type'],
                        'sample_text': f"{len(texts)} paragraphs",
                        'is_array': True
                    }
                
            # Add the main field
            processed_selections[field] = {
                'selector': data['selector'],
                'selector_type': data['selector_type'],
                'sample_text': data['sample_text']
            }
            
        self.selections = processed_selections
        return processed_selections
        
    async def build_scraper_interactively(self):
        """
        Build a scraper interactively using the UI
        
        Returns:
            dict: The selected elements
        """
        # Wait for the user to make their selections
        ui_selections = await self.wait_for_selections()
        
        # Process the selections
        await self.process_ui_selections(ui_selections)
        
        return self.selections
        
    def get_selections(self) -> Dict:
        """
        Get the current selections
        
        Returns:
            dict: The current selections
        """
        return self.selections
        
    async def save_config(self, config_path: str = None):
        """
        Save the scraper configuration to a file
        
        Args:
            config_path (str): Path to save the configuration to
            
        Returns:
            str: Path to the saved configuration file
        """
        if not config_path:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_path = os.path.join(base_dir, 'config', 'scrapers', f'{self.source_id}.json')
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            
        config = {
            'source_id': self.source_id,
            'base_url': self.base_url,
            'selectors': self.selections
        }
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
            
        logger.info(f"Saved configuration to {config_path}")
        return config_path
        
    def generate_scraper_code(self, template_path: str = None) -> str:
        """
        Generate scraper code based on the selections
        
        Args:
            template_path (str): Path to the Jinja2 template for the scraper
            
        Returns:
            str: The generated scraper code
        """
        if not template_path:
            # Use default template embedded in this file
            template_str = '''#!/usr/bin/env python3
import os
import re
from typing import Dict, Any, Optional
from bs4 import BeautifulSoup
import requests

from scrapers.base import BaseArticleScraper

class {{ source_id.capitalize() }}Scraper(BaseArticleScraper):
    """
    Scraper for {{ source_id }} articles.
    This scraper was automatically generated by the ScraperBuilder.
    """
    
    def __init__(self, proxy_type: str = 'auto'):
        """
        Initialize the {{ source_id }} scraper
        
        Args:
            proxy_type (str): Proxy type to use: 'none', 'static', 'residential', or 'auto'
        """
        super().__init__(source_id='{{ source_id }}', proxy_type=proxy_type)
        
    def scrape_article(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Scrape a {{ source_id }} article
        
        Args:
            url (str): URL of the article to scrape
            
        Returns:
            dict or None: Article data including full text and metadata, or None if scraping failed
        """
        try:
            # Get the article HTML
            response = self.http_client.get(url, headers=self.headers)
            if not response.ok:
                self.logger.error(f"Failed to fetch article {url}: {response.status_code}")
                return None
                
            # Parse the HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract article data
            article_data = {
                'url': url,
                'id': self.get_article_id_from_url(url),
                'source_id': '{{ source_id }}',
            }
            
            # Extract fields using the configured selectors
            {% for field, data in selections.items() %}
            try:
                {% if data.is_array %}
                # This is a multi-element field (like content_paragraphs)
                {{ field }}_elements = soup.select('{{ data.selector }}')
                if {{ field }}_elements:
                    {{ field }}_items = []
                    for element in {{ field }}_elements:
                        text = self._extract_text_with_links(element, '{{ base_url }}')
                        if text.strip():  # Only add non-empty items
                            {{ field }}_items.append(text)
                    
                    article_data['{{ field }}'] = {{ field }}_items
                    self.logger.debug(f"Extracted {{ field }}: {len({{ field }}_items)} items")
                else:
                    self.logger.warning(f"Could not find any {{ field }} elements using selector: {{ data.selector }}")
                {% else %}
                {% if data.selector_type == 'css' %}
                {{ field }}_element = soup.select_one('{{ data.selector }}')
                {% else %}
                from bs4 import SoupStrainer
                import lxml
                {{ field }}_element = soup.find(lambda tag: tag.name == '{{ data.selector.split("/")[-1].split("[")[0] }}')
                {% endif %}
                if {{ field }}_element:
                    article_data['{{ field }}'] = self._extract_text_with_links({{ field }}_element, '{{ base_url }}')
                    self.logger.debug(f"Extracted {{ field }}: {article_data['{{ field }}'][:100]}...")
                else:
                    self.logger.warning(f"Could not find {{ field }} element using selector: {{ data.selector }}")
                {% endif %}
            except Exception as e:
                self.logger.error(f"Error extracting {{ field }}: {e}")
            {% endfor %}
            
            # Join content paragraphs into a single content field if needed
            {% if 'content_paragraphs' in selections and 'content' not in selections %}
            if 'content_paragraphs' in article_data and isinstance(article_data['content_paragraphs'], list):
                article_data['content'] = '\n\n'.join(article_data['content_paragraphs'])
                self.logger.debug(f"Created content field from paragraphs: {article_data['content'][:100]}...")
            {% endif %}
            
            # Clean up any extracted data as needed
            {% if 'published_date' in selections %}
            # Clean up and parse the date
            if 'published_date' in article_data:
                try:
                    # Try to extract a date in common formats
                    date_text = article_data['published_date']
                    
                    # Remove common prefixes
                    date_text = re.sub(r'^(Published|Posted|Updated|Date):?\\s*', '', date_text)
                    
                    # TODO: Add date parsing logic specific to {{ source_id }}
                    # This is a placeholder that will need to be customized
                    from dateutil import parser
                    try:
                        parsed_date = parser.parse(date_text)
                        article_data['published_date'] = parsed_date.isoformat()
                    except:
                        self.logger.warning(f"Could not parse date: {date_text}")
                except Exception as e:
                    self.logger.error(f"Error parsing date: {e}")
            {% endif %}
            
            return article_data
            
        except Exception as e:
            self.logger.error(f"Error scraping article {url}: {e}")
            return None
'''
            template = jinja2.Template(template_str)
        else:
            # Load template from file
            with open(template_path, 'r') as f:
                template = jinja2.Template(f.read())
                
        # Generate code from template
        code = template.render(
            source_id=self.source_id,
            base_url=self.base_url,
            selections=self.selections
        )
        
        return code
        
    async def update_sources_yaml(self):
        """
        Update the sources.yaml file to include the new scraper
        
        Returns:
            bool: True if successful
        """
        try:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            sources_yaml_path = os.path.join(base_dir, 'config', 'sources.yaml')
            
            # Read the current YAML file
            with open(sources_yaml_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Check if the source is already in the file
            source_id_pattern = f"\n  {self.source_id}:"
            if source_id_pattern in content:
                logger.info(f"Source {self.source_id} already exists in sources.yaml")
                return True
                
            # Add scraper entry
            import re
            class_name = f"{self.source_id.capitalize()}Scraper"
            
            # Add to scrapers section
            scrapers_section = "# Article content extraction components\nscrapers:"
            scrapers_entry = f"""
  # {self.source_id.capitalize()} (https://{self.source_id}.co.uk)
  {self.source_id}:
    module: scrapers.{self.source_id}
    class: {class_name}
    description: {self.source_id.capitalize()} article content scraper
    """
            
            # Find the last scraper entry
            last_scraper_pattern = r"(\n  \w+:\n.*?class:.*?\n.*?description:.*?\n)"
            scrapers_matches = list(re.finditer(last_scraper_pattern, content, re.DOTALL))
            
            if scrapers_matches:
                last_match = scrapers_matches[-1]
                # Insert after the last scraper
                position = last_match.end()
                new_content = content[:position] + scrapers_entry + content[position:]
                
                # Write back to the file
                with open(sources_yaml_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                    
                logger.info(f"Updated sources.yaml with {self.source_id} scraper")
                return True
            else:
                logger.warning(f"Could not find scrapers section in sources.yaml")
                return False
                
        except Exception as e:
            logger.error(f"Error updating sources.yaml: {e}")
            return False
    
    async def save_scraper_code(self, save_path: str = None) -> str:
        """
        Save the generated scraper code to a file
        
        Args:
            save_path (str): Path to save the scraper code to
            
        Returns:
            str: Path to the saved scraper file
        """
        code = self.generate_scraper_code()
        
        if not save_path:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            save_path = os.path.join(base_dir, 'scrapers', f'{self.source_id}.py')
            
        with open(save_path, 'w', encoding='utf-8') as f:
            f.write(code)
            
        # Update the sources.yaml file
        await self.update_sources_yaml()
            
        logger.info(f"Saved scraper code to {save_path}")
        return save_path
        
# Command-line interface for the scraper builder
async def interactive_builder(source_id: str, url: str):
    """
    Run the interactive scraper builder with a UI panel
    
    Args:
        source_id (str): Unique identifier for the source
        url (str): URL of an example article to use for building the scraper
    """
    try:
        # Create the builder
        builder = ScraperBuilder(source_id)
        
        # Set up the interactive UI
        await builder.setup_interactive_mode(url)
        
        # Display instructions
        logger.info("Browser launched with interactive UI")
        logger.info("Use the panel on the right side to select fields")
        logger.info("For content with multiple paragraphs, use the 'Multi-select mode' option")
        logger.info("Click 'Generate Scraper' when finished")
        
        # Wait for the user to build the scraper interactively
        await builder.build_scraper_interactively()
        
        # Save configuration and generate scraper
        config_path = await builder.save_config()
        scraper_path = await builder.save_scraper_code()
        
        # Show success message in the browser
        await builder.page.evaluate("""() => {
            window.scraperBuilder.showStatus(
                'Scraper generated successfully! You can close this window.',
                10000
            );
        }""")
        
        logger.info("\n===== Scraper Builder Complete =====")
        logger.info(f"Configuration saved to: {config_path}")
        logger.info(f"Scraper code saved to: {scraper_path}")
        
        # Show a completion message and wait for user to close window
        logger.info("You can now close the browser window.")
        
        # Wait a few seconds before closing automatically
        await asyncio.sleep(10)
        
        # Close the browser
        await builder.close()
        
        return {
            'config_path': config_path,
            'scraper_path': scraper_path,
            'selections': builder.get_selections()
        }
    except Exception as e:
        logger.error(f"Error in interactive builder: {e}")
        # Try to close the browser if it exists
        try:
            if 'builder' in locals() and builder:
                await builder.close()
        except:
            pass
        raise
    
# Synchronous wrapper for the interactive builder
def run_interactive_builder(source_id: str, url: str):
    """
    Run the interactive scraper builder (synchronous wrapper)
    
    Args:
        source_id (str): Unique identifier for the source
        url (str): URL of an example article to use for building the scraper
        
    Returns:
        dict: Information about the generated scraper
    """
    return asyncio.run(interactive_builder(source_id, url))