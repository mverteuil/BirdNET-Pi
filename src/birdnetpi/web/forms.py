from wtforms import Form, SelectField, SubmitField
from wtforms.validators import InputRequired


class AudioDeviceSelectionForm(Form):
    """Form for selecting an audio device."""

    device = SelectField("Audio Device", choices=[], validators=[InputRequired()])
    submit = SubmitField("Save")
