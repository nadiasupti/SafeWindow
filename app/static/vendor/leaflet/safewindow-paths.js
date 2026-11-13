// SafeWindow's own file, not part of Leaflet. Leaflet guesses its image folder from the stylesheet link
// when the stylesheet is not applied yet, and then asks for a file that does not exist. Say where they are.
if (window.L && L.Icon && L.Icon.Default) { L.Icon.Default.imagePath = '/app/static/vendor/leaflet/images/'; }
