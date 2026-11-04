const test = require('node:test');
const assert = require('node:assert/strict');
const { classify, permitted } = require('./scanner.js');
test('recognizes explicit basic fields including ATS name ids', () => {
  assert.equal(classify({label: 'First Name', id: 'first_name'}), 'first_name');
  assert.equal(classify({label: 'Last Name', autocomplete: 'family-name'}), 'last_name');
  assert.equal(classify({label: 'Email address', type: 'email'}), 'email');
  assert.equal(classify({label: 'LinkedIn Profile URL'}), 'linkedin');
  assert.equal(classify({label: 'Portfolio / personal website'}), 'portfolio');
  assert.equal(classify({label: 'Current location'}), 'location');
});
test('never classifies sensitive or attestation questions', () => {
  for (const label of ['Work authorization email', 'Gender', 'Veteran status', 'Password', 'Visa sponsor phone', 'Expected salary', 'Legal full name signature', 'Consent agree', 'Date of birth', 'Cover letter', 'Citizenship', 'Disability', 'Street address']) assert.equal(classify({label}), null, label);
  assert.equal(classify({label: 'Tell us about yourself'}), null);
});
test('only visible editable empty basic input types are permitted', () => {
  const field = {type:'text',value:'',visible:true,disabled:false,readOnly:false};
  assert.equal(permitted(field), true);
  for (const changes of [{value:'Existing text'}, {visible:false}, {disabled:true}, {readOnly:true}, {type:'file'}, {type:'password'}, {type:'checkbox'}, {type:'submit'}, {type:'hidden'}, {type:'number'}]) assert.equal(permitted({...field, ...changes}), false);
});
test('manifest grants access only to active tab and local API', () => {
  const manifest = require('./manifest.json');
  assert.equal(manifest.manifest_version, 3);
  assert.deepEqual(manifest.permissions, ['activeTab', 'scripting', 'storage']);
  assert.deepEqual(manifest.host_permissions, ['http://127.0.0.1:8010/*']);
  assert.equal(manifest.content_scripts, undefined);
});
