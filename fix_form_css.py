import os

def fix_form(path):
    with open(path, 'r', encoding='utf-8') as f:
        html = f.read()

    # Fix label nesting
    html = html.replace('<label class="font-medium text-sm text-on-surface-variant {% if field.field.is_required %}required{% endif %}">\n                                        {{ field.label_tag }}\n                                    </label>',
                        '<div class="font-medium text-sm text-on-surface-variant {% if field.field.is_required %}required{% endif %}">\n                                        {{ field.label_tag }}\n                                    </div>')

    # Fix input styling wrapper
    bad_classes = '[&>input]:w-full [&>input]:px-3 [&>input]:py-2 [&>input]:rounded-lg [&>input]:border [&>input]:border-outline-variant [&>input]:bg-surface [&>input:focus]:ring-primary [&>select]:w-full [&>select]:px-3 [&>select]:py-2 [&>select]:rounded-lg [&>select]:border [&>select]:border-outline-variant [&>select]:bg-surface [&>textarea]:w-full [&>textarea]:px-3 [&>textarea]:py-2 [&>textarea]:rounded-lg [&>textarea]:border [&>textarea]:border-outline-variant [&>textarea]:bg-surface'
    
    good_classes = '[&>input:not([type=checkbox])]:w-full [&>input:not([type=checkbox])]:px-3 [&>input:not([type=checkbox])]:py-2 [&>input:not([type=checkbox])]:rounded-lg [&>input:not([type=checkbox])]:border [&>input:not([type=checkbox])]:border-outline-variant [&>input:not([type=checkbox])]:bg-surface [&>input:not([type=checkbox]):focus]:ring-primary [&>select]:w-full [&>select]:px-3 [&>select]:py-2 [&>select]:rounded-lg [&>select]:border [&>select]:border-outline-variant [&>select]:bg-surface [&>select[multiple]]:min-h-[200px] [&>textarea]:w-full [&>textarea]:px-3 [&>textarea]:py-2 [&>textarea]:rounded-lg [&>textarea]:border [&>textarea]:border-outline-variant [&>textarea]:bg-surface flex items-center gap-2'
    
    html = html.replace(bad_classes, good_classes)

    # For checkboxes, they should be vertically centered with the label if we arrange them differently, but Django's admin form rendering for checkboxes puts the input first inside the label tag sometimes, wait no.
    # Actually, Django's {{ field.field }} for a checkbox just outputs `<input type="checkbox">`.
    # And {{ field.label_tag }} outputs `<label>...`.
    # Let's see if this fixes the giant checkbox issue.

    # Fix help text spacing
    html = html.replace('<p class="text-xs text-on-surface-variant mt-1">{{ field.field.help_text|safe }}</p>',
                        '<p class="text-[11px] text-on-surface-variant mt-1 leading-tight">{{ field.field.help_text|safe }}</p>')

    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)

fix_form('F:\\extractor-citilink\\templates\\admin\\auth\\user\\change_form.html')
fix_form('F:\\extractor-citilink\\templates\\admin\\auth\\group\\change_form.html')
print("Fixed change forms.")
