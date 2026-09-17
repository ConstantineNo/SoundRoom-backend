import numpy as np
import pytest
from app.schemas.audio_recognition import RecognitionConfig
from app.services.audio_recognition import analyze, from_pcm
from tools.recognition_lab.score_compare import ScoreReference, ScoreNote, compare


def reference(audio):
    return ScoreReference(name='test',status='draft',audio_file='test.wav',audio_sha256=audio.info.sha256,
        key='1=C',meter='4/4',bpm=120,offset_seconds=0,timing_uncertainty_seconds=.1,
        interior_margin_seconds=.05,register_assumption='test only',evidence='synthetic',
        notes=[ScoreNote(beat=0,duration_beats=1,midi=69,label='6')])


def test_missing_f0_is_counted_as_missing_not_pitch_zero():
    audio=from_pcm(np.zeros(8000),8000)
    result=analyze(audio)
    report=compare(result,reference(audio))
    assert report['accepted_f0_coverage']==0
    assert report['rows'][0]['accepted_median_delta_cents'] is None
    assert report['rows'][0]['overlapping_event_count']==0


def test_reference_rejects_wrong_audio_and_overlapping_notes():
    audio=from_pcm(np.zeros(8000),8000)
    ref=reference(audio)
    other=analyze(from_pcm(np.zeros(8001),8000))
    with pytest.raises(ValueError,match='different decoded audio'):
        compare(other,ref)
    data=ref.model_dump()
    data['notes']*=2
    with pytest.raises(ValueError,match='not overlap'):
        ScoreReference.model_validate(data)
    data=ref.model_dump();data['notes'][0]['duration_beats']=5
    with pytest.raises(ValueError,match='beyond'):
        compare(analyze(audio),ScoreReference.model_validate(data))


def test_score_rests_do_not_turn_sustained_audio_into_error_verdicts():
    from tools.recognition_lab.score_compare import ScoreRest
    sr=8000
    audio=from_pcm(.3*np.sin(2*np.pi*440*np.arange(sr)/sr),sr)
    result=analyze(audio)
    ref=reference(audio)
    ref=ScoreReference.model_validate({**ref.model_dump(), 'rests':[ScoreRest(beat=1,duration_beats=1).model_dump()]})
    report=compare(result,ref)
    assert report['scope_seconds']==[0,1]
    assert report['score_rests'][0]['accepted_f0_fraction']>.9
    assert 'not a false-positive verdict' in report['score_rests'][0]['interpretation']
    assert 'not automatically errors' in report['comparison_policy']
    with pytest.raises(ValueError,match='must not overlap'):
        ScoreReference.model_validate({**ref.model_dump(), 'rests':[{'beat':.5,'duration_beats':1}]})
