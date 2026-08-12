'use strict';
'require view';
'require ui';

return view.extend({
	render: function() {
		var host = window.location.hostname;
		if (host.indexOf(':') !== -1 && host.charAt(0) !== '[')
			host = '[' + host + ']';

		var url = 'http://' + host + ':9000/';
		var button = E('button', {
			'class': 'btn cbi-button cbi-button-action',
			'click': function() { window.open(url, '_blank', 'noopener'); }
		}, [ _('Open Nginx UI') ]);

		var content = [
			E('h2', {}, [ _('Nginx UI') ]),
			E('p', {}, [
				_('Nginx UI listens on TCP port 9000. Its configuration and database stay under /etc/nginx-ui by default; set nginx-ui.main.config_path to an absolute path if you want to move them.')
			]),
			E('p', {}, [
				_('For the first sign-in secret, run: config=$(uci -q get nginx-ui.main.config_path || echo /etc/nginx-ui/app.ini); cat "${config%/*}/.install_secret"')
			]),
			E('p', {}, [ button ])
		];

		if (window.location.protocol === 'http:') {
			content.push(E('iframe', {
				'src': url,
				'style': 'width:100%;height:calc(100vh - 210px);min-height:640px;border:0;border-radius:6px;background:#fff',
				'title': 'Nginx UI'
			}));
		}
		else {
			content.push(E('div', { 'class': 'alert-message warning' }, [
				_('The embedded view is disabled while LuCI uses HTTPS because Nginx UI initially uses HTTP. Open it in a new tab or enable HTTPS in Nginx UI first.')
			]));
		}

		return E('div', {}, content);
	},

	handleSaveApply: null,
	handleSave: null,
	handleReset: null
});
