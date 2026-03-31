/**
 * Google Places Autocomplete input for address selection.
 *
 * Falls back to a plain text input when the Google Maps API is not
 * loaded (missing key or network failure). Never crashes on gibberish
 * input — predictions simply return empty.
 */
import { useState, useRef, useCallback, useEffect } from 'react';
import { useApiIsLoaded, useMapsLibrary } from '@vis.gl/react-google-maps';
import { TextInput } from '@/components/ui/TextInput';

export interface AddressSelection {
  address: string;
  city: string;
  state: string;
  zip_code: string;
  latitude: number;
  longitude: number;
  formatted_address: string;
}

interface AddressAutocompleteProps {
  onSelect: (selection: AddressSelection) => void;
  defaultValue?: string;
  label?: string;
  placeholder?: string;
  error?: string;
}

/** Parse address_components from Places API into our fields. */
function parseAddressComponents(
  components: google.maps.GeocoderAddressComponent[],
): { address: string; city: string; state: string; zip_code: string } {
  let streetNumber = '';
  let route = '';
  let city = '';
  let state = '';
  let zipCode = '';

  for (const comp of components) {
    const type = comp.types[0];
    switch (type) {
      case 'street_number':
        streetNumber = comp.long_name;
        break;
      case 'route':
        route = comp.long_name;
        break;
      case 'locality':
        city = comp.long_name;
        break;
      case 'sublocality_level_1':
        if (!city) city = comp.long_name;
        break;
      case 'administrative_area_level_1':
        state = comp.short_name;
        break;
      case 'postal_code':
        zipCode = comp.long_name;
        break;
    }
  }

  const address = [streetNumber, route].filter(Boolean).join(' ');
  return { address, city, state, zip_code: zipCode };
}

export function AddressAutocomplete({
  onSelect,
  defaultValue = '',
  label,
  placeholder = 'Start typing an address...',
  error,
}: AddressAutocompleteProps) {
  const apiIsLoaded = useApiIsLoaded();
  const placesLib = useMapsLibrary('places');

  const [inputValue, setInputValue] = useState(defaultValue);
  const [predictions, setPredictions] = useState<google.maps.places.AutocompletePrediction[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);

  const autocompleteService = useRef<google.maps.places.AutocompleteService | null>(null);
  const sessionToken = useRef<google.maps.places.AutocompleteSessionToken | null>(null);
  const placesService = useRef<google.maps.places.PlacesService | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Initialize Places services when API is loaded
  useEffect(() => {
    if (!placesLib) return;

    autocompleteService.current = new placesLib.AutocompleteService();
    sessionToken.current = new placesLib.AutocompleteSessionToken();

    // PlacesService requires a DOM element (can be a hidden div)
    const el = document.createElement('div');
    placesService.current = new placesLib.PlacesService(el);
  }, [placesLib]);

  // Close dropdown on click outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const fetchPredictions = useCallback(
    (input: string) => {
      if (!autocompleteService.current || !sessionToken.current || input.length < 3) {
        setPredictions([]);
        return;
      }

      autocompleteService.current.getPlacePredictions(
        {
          input,
          types: ['address'],
          componentRestrictions: { country: 'us' },
          sessionToken: sessionToken.current,
        },
        (results, status) => {
          if (status === google.maps.places.PlacesServiceStatus.OK && results) {
            setPredictions(results);
            setIsOpen(true);
          } else {
            setPredictions([]);
          }
        },
      );
    },
    [],
  );

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setInputValue(value);
    setActiveIndex(-1);

    // Debounce API calls
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetchPredictions(value), 300);
  };

  const selectPrediction = useCallback(
    (prediction: google.maps.places.AutocompletePrediction) => {
      if (!placesService.current) return;

      setInputValue(prediction.description);
      setIsOpen(false);
      setPredictions([]);

      placesService.current.getDetails(
        {
          placeId: prediction.place_id,
          fields: ['geometry', 'address_components', 'formatted_address'],
          sessionToken: sessionToken.current!,
        },
        (place, status) => {
          if (status !== google.maps.places.PlacesServiceStatus.OK || !place) return;

          const parsed = parseAddressComponents(place.address_components ?? []);
          const lat = place.geometry?.location?.lat() ?? 0;
          const lng = place.geometry?.location?.lng() ?? 0;

          onSelect({
            ...parsed,
            latitude: lat,
            longitude: lng,
            formatted_address: place.formatted_address ?? prediction.description,
          });

          // Refresh session token after a selection
          if (placesLib) {
            sessionToken.current = new placesLib.AutocompleteSessionToken();
          }
        },
      );
    },
    [onSelect, placesLib],
  );

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen || predictions.length === 0) return;

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setActiveIndex((prev) => Math.min(prev + 1, predictions.length - 1));
        break;
      case 'ArrowUp':
        e.preventDefault();
        setActiveIndex((prev) => Math.max(prev - 1, 0));
        break;
      case 'Enter':
        e.preventDefault();
        if (activeIndex >= 0 && activeIndex < predictions.length) {
          selectPrediction(predictions[activeIndex]);
        }
        break;
      case 'Escape':
        setIsOpen(false);
        break;
    }
  };

  // Fallback: plain text input when API is not loaded
  if (!apiIsLoaded) {
    return (
      <div>
        {label && (
          <label className="mb-1 block text-sm font-medium text-secondary-700">
            {label}
          </label>
        )}
        <TextInput
          role="textbox"
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          placeholder={placeholder}
          error={error}
        />
      </div>
    );
  }

  return (
    <div ref={containerRef} className="relative">
      {label && (
        <label className="mb-1 block text-sm font-medium text-secondary-700" htmlFor="address-autocomplete">
          {label}
        </label>
      )}
      <input
        id="address-autocomplete"
        role="combobox"
        aria-expanded={isOpen && predictions.length > 0}
        aria-autocomplete="list"
        aria-controls="address-suggestions"
        aria-activedescendant={activeIndex >= 0 ? `suggestion-${activeIndex}` : undefined}
        type="text"
        value={inputValue}
        onChange={handleInputChange}
        onKeyDown={handleKeyDown}
        onFocus={() => predictions.length > 0 && setIsOpen(true)}
        placeholder={placeholder}
        className={`w-full rounded-lg border px-3 py-2 text-sm transition-colors focus:ring-2 focus:outline-none ${
          error
            ? 'border-danger-300 focus:border-danger-500 focus:ring-danger-500/20'
            : 'border-secondary-300 focus:border-primary-500 focus:ring-primary-500/20'
        }`}
        autoComplete="off"
      />
      {error && <p className="mt-1 text-xs text-danger-600">{error}</p>}

      {isOpen && predictions.length > 0 && (
        <ul
          id="address-suggestions"
          ref={listRef}
          role="listbox"
          className="absolute z-50 mt-1 max-h-60 w-full overflow-auto rounded-lg border border-secondary-200 bg-white shadow-lg"
        >
          {predictions.map((prediction, idx) => (
            <li
              key={prediction.place_id}
              id={`suggestion-${idx}`}
              role="option"
              aria-selected={idx === activeIndex}
              className={`cursor-pointer px-3 py-2 text-sm ${
                idx === activeIndex ? 'bg-primary-50 text-primary-900' : 'text-secondary-700 hover:bg-secondary-50'
              }`}
              onMouseDown={() => selectPrediction(prediction)}
              onMouseEnter={() => setActiveIndex(idx)}
            >
              {prediction.description}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
