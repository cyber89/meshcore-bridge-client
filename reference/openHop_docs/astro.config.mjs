// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

// https://astro.build/config
export default defineConfig({
	site: 'https://docs.openhop.dev',
	integrations: [
		starlight({
			title: 'openHop Docs',
			description: 'Documentation hub for the openHop ecosystem: Core, Repeater, Modem, Home Assistant, and Unraid projects',
			favicon: '/favicon.png',
			head: [
				{ tag: 'meta', attrs: { property: 'og:image', content: '/openhop_logo.png' } },
				{ tag: 'meta', attrs: { property: 'og:image:alt', content: 'openHop logo' } },
				{ tag: 'meta', attrs: { name: 'twitter:card', content: 'summary_large_image' } },
				{ tag: 'meta', attrs: { name: 'twitter:image', content: '/openhop_logo.png' } },
				{ tag: 'meta', attrs: { name: 'twitter:image:alt', content: 'openHop logo' } },
				{
					tag: 'script',
					content: `(() => {
	try {
		if (typeof localStorage !== 'undefined' && !localStorage.getItem('starlight-theme')) {
			localStorage.setItem('starlight-theme', 'dark');
		}
	} catch {}
})();`,
				},
				{
					tag: 'script',
					content: `(() => {
	const markExternalLinks = () => {
		document.querySelectorAll('a[href]').forEach((link) => {
			const href = link.getAttribute('href');
			if (!href || href.startsWith('#') || href.startsWith('/') || href.startsWith('mailto:') || href.startsWith('tel:') || href.startsWith('javascript:')) return;

			try {
				const url = new URL(href, window.location.href);
				if (url.origin === window.location.origin) return;

				link.target = '_blank';
				const rel = new Set((link.getAttribute('rel') || '').split(/\\s+/).filter(Boolean));
				rel.add('noopener');
				rel.add('noreferrer');
				link.setAttribute('rel', [...rel].join(' '));
			} catch {}
		});
	};

	if (document.readyState === 'loading') {
		document.addEventListener('DOMContentLoaded', markExternalLinks, { once: true });
	} else {
		markExternalLinks();
	}
})();`,
				},
			],
			components: {
				SocialIcons: './src/components/SocialIcons.astro',
			},
			logo: {
				light: './src/assets/openhop-logo.png',
				dark: './src/assets/openhop-logo.png',
				replacesTitle: false,
			},
			customCss: ['./src/styles/brand.css'],
			social: [
				{ icon: 'github', label: 'openHop on GitHub', href: 'https://github.com/openhop-dev' },
			],
			editLink: {
				baseUrl: 'https://github.com/openhop-dev/openHop_docs/edit/main/',
			},
			sidebar: [
				{
					label: 'Projects',
					items: [
						{
							label: 'openHop Core',
							autogenerate: { directory: 'projects/openhop-core' },
						},
						{
							label: 'openHop Repeater',
							autogenerate: { directory: 'projects/openhop-repeater' },
						},
						{
							label: 'openHop Modem',
							autogenerate: { directory: 'projects/openhop-modem' },
						},
						{
							label: 'openHop HA Integration',
							autogenerate: { directory: 'projects/openhop-ha-integration' },
						},
						{
							label: 'openHop HA Add-on',
							autogenerate: { directory: 'projects/openhop-ha-addon' },
						},
						{
							label: 'openHop for Unraid',
							autogenerate: { directory: 'projects/openhop-unraid' },
						},
					],
				},
				{
					label: 'About this Documentation',
					collapsed: true,
					items: [
						{ label: 'Overview', slug: '' },
						{ label: 'Contributing', slug: 'contributing' },
					],
				},
			],
		}),
	],
});
