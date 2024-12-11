module.exports = {
  "autodiscover": false,
  "allowPostUpgradeCommandTemplating": true,
  "automerge": true,

  "repositories": [
    "wesley-dean-flexion/pre-commit-checker"
  ],

  "packageRules": [
    {
      "matchUpdateTypes": ["minor", "patch", "pin", "digest"],
      "automerge": true
    }
  ],

  "labels": [
    "dependencies"
  ]

};
