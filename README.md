# GAP - Competitor Intelligence

GAP is a web-based project designed to help users explore competitor activities, business developments, and market trends. It allows users to ask questions and receive answers along with available source information.

The idea behind GAP is to make competitor research easier by bringing relevant information into one place. Instead of looking only at an answer, users can also explore the sources associated with it and learn more about the information being presented.

## Live Demo

You can access the deployed application here:

**Website:** https://gap-frontend-mu.vercel.app

The frontend is hosted on Vercel, and the backend is hosted on Render.

## About the Project

In today's business environment, companies frequently introduce new products, expand into new markets, and compete with other businesses. Keeping track of these developments can be time-consuming because relevant information may come from different sources.

GAP aims to simplify this process through a single web interface. Users can enter questions related to competitors or market developments, and the application communicates with its backend to retrieve a response.

The project also displays available source information so that users can explore the original material behind an answer. This makes it easier to investigate business claims instead of relying only on a generated response.

## Features

**1. Question-based search**

Users can enter questions related to companies, competitors, and market developments through the web interface.

**2. Answers through the backend**

The frontend sends requests to the connected backend API, which processes them and returns the available response.

**3. Source information**

The application can display source details returned by the backend, such as article titles, dates, and links. Users can open these links to explore the original information.

**4. Competitor research**

GAP is intended to help users explore company activities and understand developments that may be relevant to competitors and their markets.

**5. Simple web interface**

The application runs in a web browser, so users do not need to install a separate desktop application.

**6. Online deployment**

The frontend and backend are deployed separately, allowing the website to communicate with the hosted API.

## Technologies Used

The frontend is built using HTML, CSS, and JavaScript. HTML provides the structure of the webpage, CSS is used for styling and layout, and JavaScript handles the interactive parts of the interface and communication with the backend.

The application uses a backend API to process questions and return responses. The backend is hosted on Render, while the frontend is deployed on Vercel. GitHub is used to store and manage the project's source code.

## How It Works

The application follows a simple process:

1. The user opens the GAP website in a browser.
2. The user enters a question related to a competitor or market development.
3. The frontend sends the request to the backend API.
4. The backend processes the request and returns the available answer and source information.
5. The frontend displays the response on the website.
6. The user can explore the returned source links for more information.

This process connects the user interface with the backend and allows the application to retrieve responses without requiring users to interact with the API directly.

## Project Structure

The frontend contains the files responsible for displaying the website, managing its appearance, and communicating with the backend.

- `index.html` contains the main webpage.
- `styles.css` contains the styling and layout of the website.
- `config.js` stores the frontend configuration, including the backend API URL.
- `js/` contains JavaScript files used for application functionality.
- `data/` contains frontend data files.
- `README_FRONTEND.md` contains additional frontend documentation.

## Running the Project Locally

To run the frontend on your computer, you need Python 3 and a modern web browser.

**Step 1: Clone the repository**

Open a terminal and run:

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd <YOUR_REPOSITORY_NAME>
```

Replace the placeholders with your actual GitHub repository URL and repository name.

**Step 2: Open the frontend directory**

If your repository contains a separate `frontend` folder, run:

```bash
cd frontend
```

If `index.html` is already in the repository's root directory, you can skip this step.

**Step 3: Check the backend configuration**

Open `config.js` and make sure the backend URL points to your deployed backend.

The current configuration is:

```javascript
window.GAP_CONFIG = {
  API_BASE: "https://backend-gap.onrender.com",
  API_PROBE_MS: 1200,
};
```

**Step 4: Start the local server**

Run the following command from the directory containing `index.html`:

```bash
python3 -m http.server 5500
```

Once the server starts, open the following address in your browser:

`http://localhost:5500`

The frontend should now be available locally, provided the configuration and backend connection are working correctly.

## Backend API

GAP communicates with its deployed backend at:

https://backend-gap.onrender.com

The question-answering endpoint used during testing is `POST /ask/eternal`.

The endpoint accepts a request and can return a response containing an answer and associated source records. These records may include details such as a source identifier, title, date, and URL.

The frontend uses the backend response to display information to the user. The actual response depends on the request and the data returned by the backend.

## Testing

The application can be tested by opening the live website and submitting different questions related to competitors or business developments.

During testing, it is useful to check whether the website loads correctly, whether questions receive responses, and whether the frontend can communicate with the deployed backend. The returned answers and source details should also be checked to ensure they appear correctly.

Source links should be opened to verify that they lead to the intended pages. The application should also be tested when a request fails or the backend is temporarily unavailable.

## Limitations

The quality of the information displayed by GAP depends on the data and responses available from the backend. Some information may be incomplete, outdated, or unavailable.

The presence of a source link does not automatically prove that every claim in an answer is correct. Users should review the original sources and compare information where necessary, especially before relying on important business claims.

The project can be improved further by expanding its research capabilities, improving source analysis, and testing it with a wider range of questions.

## Future Improvements

There are several features that could be added in future versions of GAP.

- Adding options to compare multiple competitors.
- Improving how source information is displayed.
- Identifying conflicting information across different sources.
- Adding filters for dates and types of business developments.
- Providing clearer explanations of the evidence supporting an answer.
- Improving error handling and testing for different situations.
- Expanding the types of questions the application can handle.

These improvements could make GAP more useful for users who want to research competitors and follow changes in different markets.

## Conclusion

GAP is a project focused on making competitor research easier through a simple web interface connected to a backend API. It allows users to ask questions, view available answers, and explore related source information.

The project provides a starting point for investigating business developments and understanding the information behind market-related claims. Further improvements can make the application more useful, reliable, and informative.
