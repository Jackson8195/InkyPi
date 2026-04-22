#!/bin/bash

echo "Updating Select2 CSS..."
curl -L https://cdnjs.cloudflare.com/ajax/libs/select2/4.1.0-beta.1/css/select2.min.css -o src/static/styles/select2.min.css

echo "Updating Select2 JS..."
curl -L https://cdnjs.cloudflare.com/ajax/libs/select2/4.1.0-beta.1/js/select2.min.js -o src/static/scripts/select2.min.js

echo "Updating jQuery..."
curl -L https://code.jquery.com/jquery-3.6.0.min.js -o src/static/scripts/jquery.min.js

echo "Updating Chart JS"
curl -L https://cdn.jsdelivr.net/npm/chart.js -o src/static/scripts/chart.js

echo "Updating fullcalendar JS"
curl -L https://cdn.jsdelivr.net/npm/fullcalendar@6.1.17/index.global.min.js -o src/static/scripts/calendar.min.js

echo "Updating Permanent Marker font..."
curl -s https://fonts.gstatic.com/s/permanentmarker/v16/Fh4uPib9Iyv2ucM6pGQMWimMp004Hao.ttf -o src/static/fonts/PermanentMarker-Regular.ttf

echo "All vendor files updated."
