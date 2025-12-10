"""
Score service for handling business logic related to musical scores.
"""

from music21 import converter, note, chord, meter, key, tempo

def parse_abc_to_json(abc_content: str) -> dict:
    """
    Parse ABC notation string into a structured JSON dictionary.
    
    Args:
        abc_content: The ABC notation string.
        
    Returns:
        A dictionary containing metadata and structured note data.
        
    Raises:
        ValueError: If parsing fails.
    """
    try:
        # Load ABC content
        # forceSource=True tells music21 to treat the string as content, not a filename
        score = converter.parse(abc_content, format='abc', forceSource=True)
        
        # Handle Opus (collection of scores)
        from music21 import stream
        if isinstance(score, stream.Opus):
            score = score[0]
            
    except Exception as e:
        raise ValueError(f"Failed to parse ABC content: {str(e)}")

    # Extract Metadata
    metadata = {
        "title": score.metadata.title if score.metadata and score.metadata.title else "Unknown",
        "composer": score.metadata.composer if score.metadata and score.metadata.composer else "Unknown",
    }
    
    # Extract Key
    key_objs = score.flatten().getElementsByClass(key.KeySignature)
    if key_objs:
        metadata["key"] = key_objs[0].asKey().name
    else:
        metadata["key"] = "C" # Default

    # Extract Time Signature
    ts_objs = score.flatten().getElementsByClass(meter.TimeSignature)
    if ts_objs:
        metadata["meter"] = ts_objs[0].ratioString
    else:
        metadata["meter"] = "4/4"
        
    # Extract Tempo
    mm_objs = score.flatten().getElementsByClass(tempo.MetronomeMark)
    if mm_objs:
        metadata["tempo"] = mm_objs[0].number
    else:
        metadata["tempo"] = 120

    # Extract Measures and Notes
    measures_data = []
    
    # Iterate through parts (usually just one in simple ABC)
    # We take the first part
    part = score.parts[0] if score.parts else score
    
    measures = part.getElementsByClass('Measure')
    if not measures:
        # Fallback: try to make measures or look for notes directly
        # For now, let's just create a dummy measure with all notes if no measures found
        # This is common if 'measure' objects aren't created by parser
        notes = part.flatten().notes
        if notes:
            measure_dict = {"number": 1, "notes": []}
            for elem in notes:
                if isinstance(elem, note.Note):
                     measure_dict["notes"].append({
                        "type": "note",
                        "pitch": elem.nameWithOctave,
                        "duration": float(elem.duration.quarterLength)
                    })
            measures_data.append(measure_dict)
    
    for m in measures:
        measure_dict = {
            "number": m.number,
            "notes": []
        }
        
        for elem in m.notesAndRests:
            if isinstance(elem, note.Note):
                measure_dict["notes"].append({
                    "type": "note",
                    "pitch": elem.nameWithOctave,
                    "duration": float(elem.duration.quarterLength)
                })
            elif isinstance(elem, note.Rest):
                measure_dict["notes"].append({
                    "type": "rest",
                    "duration": float(elem.duration.quarterLength)
                })
            elif isinstance(elem, chord.Chord):
                # For flute (monophonic), likely won't have chords, but handle gracefully
                # Just take the top note
                measure_dict["notes"].append({
                    "type": "note", # Treat as single note for simplicity or extend later
                    "pitch": elem.notes[-1].nameWithOctave,
                    "duration": float(elem.duration.quarterLength),
                    "is_chord": True
                })
        
        measures_data.append(measure_dict)

    return {
        "meta": metadata,
        "measures": measures_data
    }
