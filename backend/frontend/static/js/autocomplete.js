// Autocomplete functionality for PR search
document.addEventListener('DOMContentLoaded', function() {
    const searchInput = document.getElementById('pr_input');
    const form = document.getElementById('analyze-form');
    
    if (!searchInput) {
        console.error('PR input element not found');
        return;
    }
    
    // Find the existing autocomplete container or create one if it doesn't exist
    const searchBar = searchInput.closest('.search-bar');
    let autocompleteContainer = searchInput.closest('.autocomplete-container');
    
    if (!autocompleteContainer) {
        console.log('Creating new autocomplete container');
        // Create autocomplete container
        autocompleteContainer = document.createElement('div');
        autocompleteContainer.className = 'autocomplete-container';
        
        // Restructure the DOM
        searchBar.insertBefore(autocompleteContainer, searchInput);
        autocompleteContainer.appendChild(searchInput);
    } else {
        console.log('Using existing autocomplete container');
    }
    
    // Check if dropdown already exists, create if not
    let autocompleteDropdown = autocompleteContainer.querySelector('.autocomplete-dropdown');
    if (!autocompleteDropdown) {
        autocompleteDropdown = document.createElement('div');
        autocompleteDropdown.className = 'autocomplete-dropdown';
        autocompleteContainer.appendChild(autocompleteDropdown);
    }
    
    // Variables for debouncing
    let debounceTimer;
    const DEBOUNCE_DELAY = 300; // ms
    
    // Current active item index
    let activeItemIndex = -1;
    
    // Listen for input changes to trigger autocomplete
    searchInput.addEventListener('input', function() {
        clearTimeout(debounceTimer);
        
        const query = searchInput.value.trim();
        console.log('Input changed:', query);
        
        if (query.length < 2) { // Require at least 2 characters
            hideAutocomplete();
            return;
        }
        
        debounceTimer = setTimeout(() => {
            fetchAutocompleteResults(query);
        }, DEBOUNCE_DELAY);
    });
    
    // Handle keyboard navigation
    searchInput.addEventListener('keydown', function(e) {
        const items = autocompleteDropdown.querySelectorAll('.autocomplete-item');
        
        if (!autocompleteDropdown.classList.contains('show') || items.length === 0) {
            return;
        }
        
        // Down arrow
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            activeItemIndex = Math.min(activeItemIndex + 1, items.length - 1);
            updateActiveItem(items);
        }
        // Up arrow
        else if (e.key === 'ArrowUp') {
            e.preventDefault();
            activeItemIndex = Math.max(activeItemIndex - 1, -1);
            updateActiveItem(items);
        }
        // Enter key
        else if (e.key === 'Enter' && activeItemIndex !== -1) {
            e.preventDefault();
            if (items[activeItemIndex]) {
                console.log('Selected item via keyboard:', activeItemIndex);
                items[activeItemIndex].click();
            }
        }
        // Escape key
        else if (e.key === 'Escape') {
            hideAutocomplete();
            activeItemIndex = -1;
        }
    });
    
    // Close dropdown when clicking outside
    document.addEventListener('click', function(e) {
        if (!autocompleteContainer.contains(e.target)) {
            hideAutocomplete();
        }
    });
    
    // Function to show autocomplete
    function showAutocomplete() {
        autocompleteDropdown.classList.add('show');
    }
    
    // Function to hide autocomplete
    function hideAutocomplete() {
        autocompleteDropdown.classList.remove('show');
        // Reset after animation completes
        setTimeout(() => {
            if (!autocompleteDropdown.classList.contains('show')) {
                autocompleteDropdown.innerHTML = '';
            }
        }, 300);
    }
    
    // Function to fetch autocomplete results
    async function fetchAutocompleteResults(query) {
        try {
            console.log('Fetching autocomplete for:', query);
            const response = await fetch(`/api/autocomplete?query=${encodeURIComponent(query)}`);
            
            if (!response.ok) {
                throw new Error(`Network response error: ${response.status}`);
            }
            
            const data = await response.json();
            console.log('Autocomplete response:', data);
            
            // DEBUG: Analyze suggestion structure
            if (data.suggestions && data.suggestions.length > 0) {
                console.log('First suggestion type:', typeof data.suggestions[0]);
                console.log('First suggestion sample:', data.suggestions[0]);
                
                // Check if suggestions are plain strings with PR format
                if (typeof data.suggestions[0] === 'string' && data.suggestions[0].includes('#')) {
                    console.log('Suggestions appear to be formatted strings with PR references');
                }
                
                // Check if suggestions are objects with specific properties
                if (typeof data.suggestions[0] === 'object') {
                    console.log('Suggestion properties:', Object.keys(data.suggestions[0]));
                }
            }
            
            // Reset active item
            activeItemIndex = -1;
            
            // Clear and populate the dropdown
            autocompleteDropdown.innerHTML = '';
            
            if (data.suggestions && data.suggestions.length > 0) {
                data.suggestions.forEach(suggestion => {
                    const item = document.createElement('div');
                    item.className = 'autocomplete-item';
                    
                    // Handle different suggestion formats
                    let displayText;
                    let searchValue;
                    
                    if (typeof suggestion === 'string') {
                        // If suggestion is just a string - check if it includes PR number and title
                        if (suggestion.includes(' - ')) {
                            // It might be in format "123 - PR title"
                            const prNumber = suggestion.split(' - ')[0].trim();
                            // Make sure we extract only owner/repo#pr format
                            if (suggestion.includes('/') && suggestion.includes('#')) {
                                const repoPath = suggestion.substring(0, suggestion.indexOf('#'));
                                searchValue = `${repoPath}#${prNumber}`;
                                displayText = suggestion; // Show full suggestion for display
                            } else {
                                displayText = suggestion;
                                searchValue = suggestion;
                            }
                        } else {
                            displayText = suggestion;
                            searchValue = suggestion;
                        }
                    } else if (suggestion.display) {
                        // If suggestion has a display property
                        displayText = suggestion.display;
                        // Make sure we only use the PR number part, not the title
                        if (suggestion.value && typeof suggestion.value === 'string') {
                            searchValue = suggestion.value.split(' - ')[0].trim();
                        } else {
                            searchValue = displayText;
                        }
                    } else if (suggestion.repo_owner && suggestion.repo_name && suggestion.pr_number) {
                        // If suggestion has specific PR properties - THIS IS THE EXPECTED FORMAT
                        displayText = `${suggestion.repo_owner}/${suggestion.repo_name}#${suggestion.pr_number}`;
                        if (suggestion.pr_title) {
                            displayText += ` - ${suggestion.pr_title}`;
                        }
                        searchValue = `${suggestion.repo_owner}/${suggestion.repo_name}#${suggestion.pr_number}`;
                    } else {
                        // Try to extract owner/repo#pr format if possible
                        let formattedValue = '';
                        if (suggestion.owner && suggestion.repo && suggestion.pr) {
                            formattedValue = `${suggestion.owner}/${suggestion.repo}#${suggestion.pr}`;
                        } else if (suggestion.repo_path && suggestion.pr_number) {
                            formattedValue = `${suggestion.repo_path}#${suggestion.pr_number}`;
                        }
                        
                        // Use formatted value if available, otherwise fallback to string representation
                        if (formattedValue) {
                            // Can still display title if available
                            displayText = formattedValue;
                            if (suggestion.title) {
                                displayText += ` - ${suggestion.title}`;
                            }
                            searchValue = formattedValue;
                        } else {
                            // Fallback - use whatever properties are available
                            const suggestionStr = JSON.stringify(suggestion).replace(/[{}"]/g, '');
                            displayText = suggestionStr;
                            
                            // Try to extract just the PR reference part
                            const match = suggestionStr.match(/([^\/]+\/[^\/]+#\d+)/);
                            if (match) {
                                searchValue = match[1];
                            } else {
                                searchValue = suggestionStr;
                            }
                        }
                    }
                    
                    item.innerHTML = highlightText(displayText, query);
                    
                    // Set the value when clicked
                    item.addEventListener('click', function() {
                        // Ensure we only use the PR reference format (owner/repo#number)
                        // Extract PR reference if it contains a title
                        if (searchValue.includes(' - ')) {
                            const parts = searchValue.split(' - ');
                            searchValue = parts[0].trim();
                        }
                        
                        // Double-check that it follows the expected pattern
                        const prPattern = /^[^\/]+\/[^\/]+#\d+$/;
                        if (!prPattern.test(searchValue)) {
                            console.warn('SearchValue does not match expected pattern:', searchValue);
                            
                            // Try to extract the PR reference
                            const match = searchValue.match(/([^\/]+\/[^\/]+#\d+)/);
                            if (match) {
                                searchValue = match[1];
                                console.log('Extracted PR reference:', searchValue);
                            }
                        }
                        
                        // Set the input value to the formatted owner/repo#pr string
                        searchInput.value = searchValue;
                        console.log('Selected suggestion (final):', searchValue);
                        hideAutocomplete();
                        
                        // Small delay before submitting to ensure the value is set
                        setTimeout(() => {
                            // Optional: submit the form
                            form.submit();
                        }, 10);
                    });
                    
                    autocompleteDropdown.appendChild(item);
                });
                
                showAutocomplete();
            } else {
                console.log('No suggestions found');
                hideAutocomplete();
            }
        } catch (error) {
            console.error('Error fetching autocomplete results:', error);
            hideAutocomplete();
        }
    }
    
    // Function to highlight matching text
    function highlightText(text, query) {
        if (!query) return text;
        
        // Create a regex that matches query parts, case insensitive
        const regex = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
        
        // Replace matches with highlighted span
        return text.replace(regex, '<span class="autocomplete-highlight">$1</span>');
    }
    
    // Function to update active item in dropdown
    function updateActiveItem(items) {
        for (let i = 0; i < items.length; i++) {
            if (i === activeItemIndex) {
                items[i].classList.add('active');
                
                // Scroll into view if needed
                const containerRect = autocompleteDropdown.getBoundingClientRect();
                const itemRect = items[i].getBoundingClientRect();
                
                if (itemRect.bottom > containerRect.bottom) {
                    autocompleteDropdown.scrollTop += (itemRect.bottom - containerRect.bottom);
                } else if (itemRect.top < containerRect.top) {
                    autocompleteDropdown.scrollTop -= (containerRect.top - itemRect.top);
                }
            } else {
                items[i].classList.remove('active');
            }
        }
    }
    
    // Log to confirm script loaded
    console.log('Autocomplete script initialized');
});
