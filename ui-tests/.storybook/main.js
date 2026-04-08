/** @type { import('@storybook/html-vite').StorybookConfig } */
const config = {
  stories: [
    '../stories/**/*.stories.@(js|jsx|ts|tsx)',
  ],
  addons: [
    '@storybook/addon-essentials',
    '@storybook/addon-a11y',
  ],
  framework: {
    name: '@storybook/html-vite',
    options: {},
  },
  docs: {
    autodocs: 'tag',
  },
  // Serve the portal's actual CSS so stories render with production styles
  viteFinalConfig: {
    server: {
      fs: {
        allow: ['..'],
      },
    },
  },
};

export default config;
